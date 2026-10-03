import assert from 'node:assert/strict';
import test from 'node:test';
import {
  JOUR7_CONFIG_KEY, PUBLISH_JITTER_MINUTES, jour7DueMinute, jour7Operation, publishJitter, runScheduler, schedulerOperations,
} from '../src/scheduler.js';

function configuration() {
  return {
    timeZone: 'Europe/Paris', dryRun: false, publishJitterMinutes: 0,
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

test('the publication minute moves with the day instead of being the same minute forever', () => {
  const config = configuration();
  delete config.publishJitterMinutes;
  const slotOf = (instant) => schedulerOperations(config, new Date(instant))
    .find((operation) => operation.inputs.publish_slot === '18:00');

  // Same day, same answer: the scheduler runs on a loop, and an offset drawn
  // afresh on every tick would make a slot flicker in and out of being due.
  const first = slotOf('2026-08-28T16:00:00Z');
  assert.equal(first.dueMinute, slotOf('2026-08-28T19:00:00Z').dueMinute);
  assert.equal(first.dueMinute, (18 * 60) + publishJitter('2026-08-28', '18:00'));
  assert.equal(first.windowStart, first.dueMinute);
  // The slot keeps its identity, because the runner matches on it.
  assert.equal(first.id, 'daily-publish');
  assert.equal(first.inputs.publish_slot, '18:00');

  const minutes = new Set();
  for (let day = 1; day <= 28; day += 1) {
    const date = `2026-09-${String(day).padStart(2, '0')}`;
    const offset = publishJitter(date, '18:00');
    assert.ok(offset >= 0 && offset < PUBLISH_JITTER_MINUTES);
    minutes.add(offset);
  }
  assert.ok(minutes.size >= 20, 'four weeks of publications spread across the hour');

  config.publishJitterMinutes = 0;
  assert.equal(slotOf('2026-08-28T16:00:00Z').dueMinute, 18 * 60);
  config.publishJitterMinutes = 10;
  assert.ok(slotOf('2026-08-28T16:00:00Z').dueMinute - (18 * 60) < 10);
});

test('Jour 7 posts at a different hour every day, anywhere inside its window', () => {
  const hours = [];
  for (let offset = 0; offset < 120; offset += 1) {
    const date = new Date(Date.UTC(2026, 9, 1) + (offset * 86_400_000)).toISOString().slice(0, 10);
    const minute = jour7DueMinute(date);
    assert.ok(minute >= 9 * 60 && minute < 22 * 60, `${date} falls inside 09:00-22:00`);
    hours.push(Math.floor(minute / 60));
  }
  for (let index = 1; index < hours.length; index += 1) {
    assert.notEqual(hours[index], hours[index - 1], 'never the same hour two days running');
  }
  assert.equal(new Set(hours).size, 13, 'four months reach every hour of the window');
  assert.equal(jour7DueMinute('2026-11-05'), jour7DueMinute('2026-11-05'));
  assert.ok(jour7DueMinute('2026-11-05', '12:00', '14:00') >= 12 * 60);
  assert.throws(() => jour7DueMinute('2026-11-05', '12:00', '12:30'), /Invalid Jour 7 window/u);
});

test('Jour 7 is off until its configuration says otherwise, then due once a day', () => {
  const now = new Date('2026-10-04T08:00:00Z');
  assert.equal(jour7Operation(null, now), null);
  assert.equal(jour7Operation({ enabled: false }, now), null);
  const operation = jour7Operation({ enabled: true }, now);
  assert.equal(operation.workflow, 'jour7-publish.yml');
  assert.equal(operation.inputs.schedule_date, '2026-10-04');
  assert.equal(operation.inputs.dry_run, 'false');
  assert.equal(operation.dueMinute, jour7DueMinute('2026-10-04'));
  const atDue = new Date(Date.parse('2026-10-04T00:00:00+02:00') + (operation.dueMinute * 60_000));
  assert.equal(jour7Operation({ enabled: true }, new Date(atDue.getTime() - 60_000)).eligible, false);
  assert.equal(jour7Operation({ enabled: true }, atDue).eligible, true);
});

test('the scheduler dispatches Jour 7 even with every ClipMaker channel paused', async () => {
  const paused = configuration();
  paused.channels.forEach((channel) => { channel.enabled = false; });
  const records = new Map();
  const dispatched = [];
  const env = {
    REPOSITORY_OWNER: 'owner', REPOSITORY_NAME: 'repo',
    CONFIG: {
      get: async (key) => ({ 'publisher-config-v1': paused, [JOUR7_CONFIG_KEY]: { enabled: true } })[key] ?? records.get(key),
      put: async (key, value) => records.set(key, JSON.parse(value)),
    },
    github: async (path, options = {}) => {
      if (options.method === 'POST') dispatched.push({ path, body: JSON.parse(options.body) });
      return { response: new Response('{}'), payload: options.method === 'POST' ? { workflow_run_id: 9 } : { workflow_runs: [] } };
    },
  };
  const results = await runScheduler({ env, token: 'test', now: new Date('2026-10-04T21:30:00Z') });
  assert.deepEqual(results.map((result) => [result.operation, result.action]), [['jour7-publish', 'dispatch']]);
  assert.match(dispatched[0].path, /jour7-publish\.yml\/dispatches$/u);
  assert.equal(dispatched[0].body.inputs.schedule_date, '2026-10-04');
  assert.equal(records.get('scheduler:2026-10-04:jour7-publish').runId, 9);
});
