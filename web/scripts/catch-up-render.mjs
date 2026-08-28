#!/usr/bin/env node
import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { isTrustedDailyRender, planRenderCatchup } from '../src/automation/render-catchup.mjs';
import { dateInTimeZone } from '../src/automation/time.mjs';

const CLOUD_API = 'https://clipmaker-cloud-control.einslen.workers.dev';

// No downloaded artifact is extracted or executed here. Only trusted default
// branch code runs with secrets; bootstrap sessions remain in memory and are
// never logged. Errors deliberately exclude HTTP bodies and credentials.
export async function catchUpRender({ event, env = process.env, request = fetch,
  clock = () => new Date(), log = console.log }) {
  const identity = { repository: env.GITHUB_REPOSITORY,
    defaultBranch: event.repository?.default_branch };
  if (env.GITHUB_EVENT_NAME !== 'workflow_run'
    || !isTrustedDailyRender(event.workflow_run, identity)) {
    log('No trusted production render to catch up.');
    return;
  }
  if (!env.GH_TOKEN || !env.CLIPMAKER_UPLOAD_TOKEN) throw new Error('Missing runner credentials.');
  const github = async (suffix, body) => {
    const response = await request(`https://api.github.com/repos/${identity.repository}/${suffix}`, {
      method: body ? 'POST' : 'GET', redirect: 'error', signal: AbortSignal.timeout(30_000),
      headers: { Authorization: `Bearer ${env.GH_TOKEN}`,
        Accept: 'application/vnd.github+json', 'Content-Type': 'application/json' },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) throw new Error(`GitHub request failed (${response.status}).`);
    return response.status === 204 ? null : response.json();
  };
  // Re-read the run via authenticated GitHub API, not just the event payload.
  const run = await github(`actions/runs/${event.workflow_run.id}`);
  if (!isTrustedDailyRender(run, identity)) throw new Error('Production render provenance changed.');
  const bootstrap = await request(`${CLOUD_API}/api/workflow/bootstrap`, {
    redirect: 'error', signal: AbortSignal.timeout(30_000),
    headers: { Authorization: `Bearer ${env.CLIPMAKER_UPLOAD_TOKEN}` },
  });
  if (!bootstrap.ok) throw new Error(`Cloud configuration unavailable (${bootstrap.status}).`);
  const { config } = await bootstrap.json();
  if (config?.dryRun !== false) { log('Catch-up disabled in dry-run mode.'); return; }
  const timeZone = config.timeZone || 'Europe/Paris';
  const now = clock();
  const today = dateInTimeZone(now, timeZone);
  if (dateInTimeZone(new Date(run.created_at), timeZone) !== today) {
    log('Expired render; no publication.'); return;
  }
  const listArtifacts = async id => {
    const items = [];
    for (let page = 1; ; page += 1) {
      const result = await github(`actions/runs/${id}/artifacts?per_page=100&page=${page}`);
      items.push(...result.artifacts);
      if (items.length >= result.total_count || result.artifacts.length < 100) return items;
    }
  };
  const artifacts = await listArtifacts(run.id);
  const availableArtifacts = [...artifacts];
  // An account-specific rerender can finish after its sibling account. Match
  // the publisher's 20-run search window and require successful trusted runs.
  const recent = await github('actions/workflows/soft-body-artifact.yml/runs'
    + `?status=success&branch=${encodeURIComponent(identity.defaultBranch)}&per_page=20`);
  for (const other of recent.workflow_runs) {
    if (other.id === run.id || !isTrustedDailyRender(other, identity)
      || dateInTimeZone(new Date(other.created_at), timeZone) !== today) continue;
    availableArtifacts.push(...await listArtifacts(other.id));
  }
  const plan = planRenderCatchup({ ...identity, run, artifacts, availableArtifacts, config, now: clock() });
  for (const dispatch of plan.dispatches) {
    await github(`actions/workflows/${dispatch.workflow}/dispatches`, {
      ref: dispatch.ref, inputs: dispatch.inputs,
    });
    log(`Publication rattrapée : ${dispatch.inputs.schedule_date} à ${dispatch.inputs.publish_slot}.`);
  }
  if (!plan.dispatches.length) log(`Aucune publication à rattraper (${plan.reason}).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  Promise.resolve().then(async () => catchUpRender({
    event: JSON.parse(await fs.readFile(process.env.GITHUB_EVENT_PATH, 'utf8')),
  })).catch(() => {
    // JSON/network errors can embed response snippets: never log bootstrap data.
    console.error('Late-render catch-up failed. No forced upload was attempted.');
    process.exitCode = 1;
  });
}
