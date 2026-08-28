import fs from 'node:fs/promises';
import path from 'node:path';
import { loadState, withStateLock } from './state.mjs';

function fullyPublished(job) {
  const targets = Object.values(job.platforms || {}).filter((target) => target.enabled);
  return job.status === 'published' && targets.length > 0
    && targets.every((target) => target.status === 'published');
}

export function publishedRenderFiles(state) {
  const safeName = (name) => typeof name === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]*\.mp4$/u.test(name);
  const pending = new Set(state.jobs.filter((job) => !fullyPublished(job)).map((job) => job.render?.filename));
  return [...new Set(state.jobs.filter(fullyPublished).map((job) => job.render?.filename))]
    .filter((name) => safeName(name) && !pending.has(name));
}

export async function cleanupPublishedRenders(config, { dryRun = config.dryRun } = {}) {
  return withStateLock(config.stateDir, async () => {
    const names = publishedRenderFiles(await loadState(config.stateDir));
    if (dryRun) return { dryRun: true, removed: [], candidates: names };
    const directory = await fs.realpath(path.resolve(path.dirname(config.configPath), '../renders'));
    const removed = [];
    for (const name of names) {
      const target = path.resolve(directory, name);
      if (path.dirname(target) !== directory) throw new Error('Unsafe published render path.');
      let stat;
      try {
        stat = await fs.lstat(target);
      } catch (error) {
        if (error.code === 'ENOENT') continue;
        throw error;
      }
      // Never recurse or follow symlinks. Pending/untracked videos are retained.
      if (!stat.isFile() || stat.isSymbolicLink()) continue;
      await fs.unlink(target);
      removed.push(name);
    }
    return { dryRun: false, removed };
  });
}
