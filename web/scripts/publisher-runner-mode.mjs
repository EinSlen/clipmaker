import fs from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

export function publisherRunnerDryRun(config, eventName, manualDryRun) {
  // A queued dispatch must not override a subsequently saved safety setting.
  // Missing/invalid configuration is safe by default; only explicit false is live.
  return config?.dryRun !== false
    || (eventName === 'workflow_dispatch' && String(manualDryRun) === 'true');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const config = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
  console.log(String(publisherRunnerDryRun(config, process.env.GITHUB_EVENT_NAME, process.env.MANUAL_DRY_RUN)));
}
