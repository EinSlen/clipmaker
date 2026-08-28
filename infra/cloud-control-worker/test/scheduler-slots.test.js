import assert from 'node:assert/strict';
import test from 'node:test';
import { runScheduler, schedulerOperations } from '../src/scheduler.js';

function configuration() {
  return {
    timeZone: 'Europe/Paris', dryRun: false,
    channels: ['18:00', '20:00', '20:00'].map((publishTime, index) => ({
      id: `channel-${index}`, enabled: true, generateTime: '00:30', publishTime,
      game: { id: 'ball-escape' },
    })),
  };
}

test('each publication slot becomes due independently, batching identical times', () => {
  const config = configuration();
  const select = (instant) => schedulerOperations(config, new Date(instant))
    .filter((operation) => operation.inputs.action === 'publish');
  const early = select('2026-08-28T16:00:00Z');
  assert.deepEqual(early.map((operation) => [operation.inputs.publish_slot, operation.eligible]), [
    ['18:00', true], ['20:00', false],
  ]);
  assert.equal(early[0].id, 'daily-publish'); // Preserve the existing 18:00 retry record.
  assert.equal(early[1].id, 'daily-publish-2000');
  assert.equal(early[0].inputs.scheduled_publish, 'true');
  assert.equal(early[0].inputs.schedule_date, '2026-08-28');
  assert.equal(select('2026-08-28T17:59:00Z')[1].eligible, false);
  assert.equal(select('2026-08-28T18:00:00Z')[1].eligible, true);
  assert.equal(select('2026-12-28T19:00:00Z')[1].eligible, true);
  config.channels[0].enabled = false;
  assert.equal(select('2026-08-28T18:00:00Z')[0].id, 'daily-publish-2000');
});

test('invalid slot values fail closed', () => {
  for (const publishTime of ['24:00', '18:60', '6:00']) {
    const config = configuration();
    config.channels[0].publishTime = publishTime;
    assert.throws(() => schedulerOperations(config, new Date()), /Invalid scheduler time/u);
  }
});

test('a completed 18:00 run and a manual generation never swallow the 20:00 slot', async () => {
  const records = new Map([['scheduler:2026-08-28:daily-publish', {
    dispatchedAt: '2026-08-28T16:00:00Z', attempts: 1, runId: 101,
  }]]);
  let runs = [{
    id: 101, head_branch: 'main', event: 'workflow_dispatch', status: 'completed',
    conclusion: 'success', created_at: '2026-08-28T16:00:01Z',
  }, {
    id: 102, head_branch: 'main', event: 'workflow_dispatch', status: 'completed',
    conclusion: 'success', created_at: '2026-08-28T18:00:01Z', display_title: 'ClipMaker · generate',
  }];
  const dispatches = [];
  const env = {
    REPOSITORY_OWNER: 'owner', REPOSITORY_NAME: 'repo',
    CONFIG: {
      get: async (key) => key === 'publisher-config-v1' ? configuration() : records.get(key),
      put: async (key, value) => records.set(key, JSON.parse(value)),
    },
    github: async (path, options = {}) => {
      if (options.method === 'POST') {
        dispatches.push(JSON.parse(options.body));
        return { response: new Response('{}'), payload: { workflow_run_id: 103 } };
      }
      assert.ok(path.includes('branch=main'));
      return { response: new Response('{}'), payload: { workflow_runs: runs } };
    },
  };
  const first = await runScheduler({ env, token: 'test', now: new Date('2026-08-28T18:00:00Z') });
  assert.deepEqual(first.map((result) => result.action), ['skip', 'dispatch']);
  assert.equal(dispatches[0].inputs.publish_slot, '20:00');
  runs = [...runs, {
    id: 103, head_branch: 'main', event: 'workflow_dispatch', status: 'completed',
    conclusion: 'success', created_at: '2026-08-28T18:00:02Z',
  }];
  const next = await runScheduler({ env, token: 'test', now: new Date('2026-08-28T18:30:00Z') });
  assert.deepEqual(next.map((result) => result.runId), [101, 103]);
  assert.equal(dispatches.length, 1);
});

test('legacy records without a run ID only match the scheduled publication title', async () => {
  const config = configuration();
  config.channels = config.channels.slice(0, 1);
  const records = new Map([['scheduler:2026-08-28:daily-publish', {
    dispatchedAt: '2026-08-28T16:00:00Z', attempts: 1,
  }]]);
  const runs = [{
    id: 104, head_branch: 'main', event: 'workflow_dispatch', status: 'completed',
    conclusion: 'success', created_at: '2026-08-28T16:00:02Z', display_title: 'ClipMaker · generate',
  }, {
    id: 105, head_branch: 'codex/test', event: 'workflow_dispatch', status: 'completed',
    conclusion: 'success', created_at: '2026-08-28T16:00:03Z', display_title: 'ClipMaker · publish 18:00',
  }];
  const env = {
    REPOSITORY_OWNER: 'owner', REPOSITORY_NAME: 'repo',
    CONFIG: {
      get: async (key) => key === 'publisher-config-v1' ? config : records.get(key),
      put: async () => {},
    },
    github: async (_path, options = {}) => ({
      response: new Response('{}'),
      payload: options.method === 'POST' ? { workflow_run_id: 106 } : { workflow_runs: runs },
    }),
  };
  const result = await runScheduler({ env, token: 'test', now: new Date('2026-08-28T16:25:00Z') });
  assert.equal(result[0].action, 'dispatch');
  runs.push({ ...runs[0], id: 107, display_title: 'ClipMaker · publish 18:00' });
  const observed = await runScheduler({ env, token: 'test', now: new Date('2026-08-28T16:26:00Z') });
  assert.equal(observed[0].runId, 107);
  assert.equal(observed[0].action, 'skip');
});
