import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const STATE_FILE = 'publisher-state.json';
const JOURNAL_FILE = 'publisher-events.jsonl';
const LOCK_DIR = '.publisher.lock';
const LOCK_STALE_MS = 48 * 60 * 60 * 1000;

export function emptyState() {
  return { version: 1, updatedAt: null, jobs: [] };
}

export async function ensureStateDir(stateDir) {
  await fs.mkdir(stateDir, { recursive: true });
}

export async function loadState(stateDir) {
  await ensureStateDir(stateDir);
  try {
    const parsed = JSON.parse(await fs.readFile(path.join(stateDir, STATE_FILE), 'utf8'));
    if (parsed?.version !== 1 || !Array.isArray(parsed.jobs)) throw new Error('Unsupported publisher state.');
    return parsed;
  } catch (error) {
    if (error?.code === 'ENOENT') return emptyState();
    throw error;
  }
}

export async function saveState(stateDir, state) {
  await ensureStateDir(stateDir);
  state.updatedAt = new Date().toISOString();
  const destination = path.join(stateDir, STATE_FILE);
  const temporary = `${destination}.${process.pid}.${Date.now()}.tmp`;
  await fs.writeFile(temporary, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
  try {
    await fs.rename(temporary, destination);
  } catch (error) {
    // POSIX rename replaces atomically. Windows refuses to replace an existing
    // destination, so keep the fallback scoped to this exact state file.
    if (!['EEXIST', 'EPERM'].includes(error?.code)) throw error;
    await fs.rm(destination, { force: true });
    await fs.rename(temporary, destination);
  }
}

export async function appendEvent(stateDir, event) {
  await ensureStateDir(stateDir);
  const record = { at: new Date().toISOString(), ...event };
  await fs.appendFile(path.join(stateDir, JOURNAL_FILE), `${JSON.stringify(record)}\n`, { mode: 0o600 });
}

async function lockIsStale(lockPath) {
  try {
    const stat = await fs.stat(lockPath);
    return Date.now() - stat.mtimeMs > LOCK_STALE_MS;
  } catch {
    return false;
  }
}

export async function withStateLock(stateDir, callback) {
  await ensureStateDir(stateDir);
  const lockPath = path.resolve(stateDir, LOCK_DIR);
  let acquired = false;
  try {
    try {
      await fs.mkdir(lockPath);
      acquired = true;
    } catch (error) {
      if (error?.code !== 'EEXIST') throw error;
      if (!(await lockIsStale(lockPath))) {
        const busy = new Error('Another publisher process is already running.');
        busy.code = 'PUBLISHER_BUSY';
        throw busy;
      }
      await fs.rm(lockPath, { recursive: true, force: true });
      await fs.mkdir(lockPath);
      acquired = true;
    }
    await fs.writeFile(
      path.join(lockPath, 'owner.json'),
      `${JSON.stringify({ pid: process.pid, host: os.hostname(), startedAt: new Date().toISOString() })}\n`,
      { mode: 0o600 },
    );
    return await callback();
  } finally {
    if (acquired) await fs.rm(lockPath, { recursive: true, force: true });
  }
}

export function pruneState(state, oldestDate) {
  state.jobs = state.jobs.filter((job) => job.date >= oldestDate || job.status !== 'published');
  return state;
}

export function publicState(state) {
  return {
    ...state,
    jobs: state.jobs.map((job) => ({
      ...job,
      render: job.render ? { ...job.render, raw: undefined } : null,
      platforms: Object.fromEntries(
        Object.entries(job.platforms || {}).map(([key, value]) => [key, { ...value, raw: undefined }]),
      ),
    })),
  };
}

export function errorMessage(error) {
  return (error instanceof Error ? error.message : String(error)).slice(0, 2000);
}
