import path from 'node:path';
import { spawn } from 'node:child_process';
import { TIKTOK_COOKIES_DIR } from '@/lib/server-paths';

export type TikTokIdentity = {
  username: string;
  ready: boolean;
  accountId: string | null;
};

export type SharedTikTokAccount = {
  accountId: string;
  usernames: string[];
};

type IdentityReport = {
  accounts?: TikTokIdentity[];
  shared?: SharedTikTokAccount[];
};

// Two logins of one TikTok account look like two accounts everywhere else in
// this project, because the only name a cookie file carries is the label
// somebody typed at login. Asking Studio for the numeric account id is the
// only way to tell them apart, and it matters: two channels pointed at one
// account publish twice a day from the same profile, which is the shape
// TikTok treats as spam.
export function readTikTokIdentities(timeoutMs = 90_000): Promise<IdentityReport> {
  return new Promise((resolve, reject) => {
    const python = process.env.PYTHON_BIN || 'python';
    const script = path.join(process.cwd(), 'scripts', 'tiktok-account-status.py');
    const proc = spawn(python, [script, TIKTOK_COOKIES_DIR, '--identity'], { windowsHide: true });
    const timer = setTimeout(() => proc.kill(), timeoutMs);
    let out = '';
    let err = '';
    proc.stdout.on('data', (data) => (out += data.toString()));
    proc.stderr.on('data', (data) => (err += data.toString()));
    proc.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error(err.trim() || `Account identity check exited with code ${code}.`));
      try {
        resolve(JSON.parse(out) as IdentityReport);
      } catch {
        reject(new Error('Account identity check returned invalid JSON.'));
      }
    });
    proc.on('error', (error) => {
      clearTimeout(timer);
      reject(error);
    });
  });
}

// Only the accounts a run would actually publish to are worth blocking on.
// An unknown identity never blocks: the check reaches the network, and a
// TikTok outage must not stop somebody saving a configuration change.
export function collidingChannels(
  report: IdentityReport,
  assignments: Array<{ channelId: string; username: string }>,
): Array<{ accountId: string; channels: string[]; usernames: string[] }> {
  const identities = new Map<string, string | null>();
  for (const account of report.accounts || []) {
    identities.set(account.username.toLocaleLowerCase('en-US'), account.accountId ?? null);
  }
  const owners = new Map<string, Array<{ channelId: string; username: string }>>();
  for (const assignment of assignments) {
    const accountId = identities.get(assignment.username.toLocaleLowerCase('en-US'));
    if (!accountId) continue;
    const group = owners.get(accountId) || [];
    group.push(assignment);
    owners.set(accountId, group);
  }
  return [...owners.entries()]
    .filter(([, group]) => new Set(group.map((item) => item.channelId)).size > 1)
    .map(([accountId, group]) => ({
      accountId,
      channels: [...new Set(group.map((item) => item.channelId))].sort(),
      usernames: [...new Set(group.map((item) => item.username))].sort(),
    }));
}
