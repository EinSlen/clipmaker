import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readPublisherConfig } from './config.mjs';
import { generateChannel, importRenderedJob, planForDate, publishChannel, runDue } from './orchestrator.mjs';
import { loadState, saveState, withStateLock } from './state.mjs';
import { buildPublisherSummary } from './summary.mjs';
import { addDays, dateInTimeZone, isTimeDue } from './time.mjs';
import { assertNative3dQuality } from './native-3d-quality.mjs';

async function temporaryDirectory(t) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'clipmaker-publisher-'));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  return directory;
}

async function repositoryFile(relativePath) {
  const candidates = [
    ...(process.env.REPO_ROOT ? [path.join(process.env.REPO_ROOT, relativePath)] : []),
    fileURLToPath(new URL(`../../../${relativePath}`, import.meta.url)),
    fileURLToPath(new URL(`../../${relativePath}`, import.meta.url)),
  ];
  for (const candidate of candidates) {
    if (await fs.stat(candidate).then((stat) => stat.isFile()).catch(() => false)) return candidate;
  }
  throw new Error(`Repository fixture not found: ${relativePath}`);
}

function sampleChannel() {
  return {
    id: 'main',
    enabled: true,
    generateTime: '00:30',
    publishTime: '18:30',
    game: { game: 'ball-escape', difficulty: 14 },
    youtube: { enabled: false, account: 'default', privacy: 'private', confirmPublic: false },
    tiktok: { enabled: false, username: null, musicId: null, visibility: 'private', confirmPublic: false },
  };
}

function native3dEvidence(seed) {
  const stages = [0, 25, 55, 75, 100];
  return {
    physics_preflight: 'passed', game: 'soft-body-slide', seed, duration: 30,
    render_width: 1080, render_height: 1920, render_fps: 30, output_fps: 30,
    frames: 900, variant_obstacle: 'peg-grid', softness_stages: stages,
    attempt_quality: stages.flatMap((softness, index) => [1, 2].map((body) => ({
      stage: index + 1, softness, attempt: 1, body,
      start_frame: index * 180 + 1, end_frame: (index + 1) * 180,
      issues: [], surface: { inside_contacts: 0 },
      framing: { frames_checked: 180, maximum_empty_seconds: 0, maximum_side_exit_seconds: 0, issues: [] },
      rendered_surface: { frames_checked: 180, vertices_checked: 210946 * 180, subdivision: 3, maximum_penetration: 0, maximum_correction: 0.01, issues: [] },
      inter_body_contact: { frames_checked: 180, maximum_penetration: 0, issues: [] },
    }))),
  };
}

test('3D upload evidence rejects missing bodies, overlaps, defects and old low-fps renders', () => {
  const expected = { seed: 123, duration: 30, obstacle: 'auto' };
  const good = native3dEvidence(123);
  assert.doesNotThrow(() => assertNative3dQuality(good, expected));
  const corrupted = [
    {}, { ...good, physics_preflight: 'failed' }, { ...good, seed: 124 },
    { ...good, render_fps: 6 }, { ...good, render_width: 432 },
    { ...good, attempt_quality: good.attempt_quality.slice(1) },
    { ...good, attempt_quality: [...good.attempt_quality, good.attempt_quality[0]] },
    { ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0 ? { ...r, issues: ['constraint-tear'] } : r) },
    { ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0 ? { ...r, surface: { inside_contacts: 1 } } : r) },
    ...[undefined, { frames_checked: 180, issues: [] },
      { frames_checked: 180, maximum_empty_seconds: 1.5, maximum_side_exit_seconds: 0, issues: [] },
      { frames_checked: 180, maximum_empty_seconds: 0, maximum_side_exit_seconds: 0.7, issues: [] },
      { frames_checked: 180, maximum_empty_seconds: Number.NaN, maximum_side_exit_seconds: 0, issues: [] },
      { frames_checked: 179, maximum_empty_seconds: 0, maximum_side_exit_seconds: 0, issues: [] },
    ].map((framing) => ({ ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0 ? { ...r, framing } : r) })),
    { ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0 ? { ...r, inter_body_contact: { frames_checked: 180, issues: ['specimens-interpenetrate'] } } : r) },
    ...[undefined, -0.01, 0.009, NaN, Infinity, '0'].map((maximum_penetration) => ({
      ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0
        ? { ...r, inter_body_contact: { frames_checked: 180, maximum_penetration, issues: [] } } : r),
    })),
    { ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0
      ? { ...r, inter_body_contact: { frames_checked: 180, maximum_penetration: 0, spine_inside_contacts: 1, issues: [] } } : r) },
    ...[
      undefined, { ...good.attempt_quality[0].rendered_surface, frames_checked: 179 },
      { ...good.attempt_quality[0].rendered_surface, subdivision: 2 },
      { ...good.attempt_quality[0].rendered_surface, maximum_penetration: 0.004 },
      { ...good.attempt_quality[0].rendered_surface, maximum_correction: 0.09 },
      { ...good.attempt_quality[0].rendered_surface, maximum_correction: Number.NaN },
    ].map((rendered_surface) => ({ ...good, attempt_quality: good.attempt_quality.map((r, i) => i === 0 ? { ...r, rendered_surface } : r) })),
    { ...good, attempt_quality: good.attempt_quality.map((r) => r.stage === 2 ? { ...r, start_frame: 180 } : r) },
  ];
  for (const evidence of corrupted) {
    assert.throws(() => assertNative3dQuality(evidence, expected), /3D publication blocked/u);
  }
});

test('stair upload requires a complete outlet beat for all three specimens', () => {
  const base = native3dEvidence(123);
  const good = { ...base, variant_obstacle: 'stair-cascade',
    attempt_quality: base.attempt_quality.filter((report) => report.body === 1).flatMap((report) =>
      [1, 2, 3].map((body) => ({ ...structuredClone(report), body,
        rendered_surface: { ...report.rendered_surface, contact_model: 'closed-stair-volume-v1',
          classification: 'independent-three-ray-parity', outside_vertices_moved: 0 },
        framing: { ...report.framing, outlet: { minimum_observation_seconds: 0.35, issues: [], bodies:
          [1, 2, 3].map((id) => ({ body: id, first_outlet_frame: 150, observation_seconds: 1, observed: true })) } },
      }))) };
  assert.doesNotThrow(() => assertNative3dQuality(good, { seed: 123 }));
  const outlet = good.attempt_quality[0].framing.outlet;
  const invalid = [undefined, { ...outlet, bodies: outlet.bodies.slice(1) }, { ...outlet, minimum_observation_seconds: 0.1 },
    ...[{ body: 2 }, { observed: false }, { first_outlet_frame: 175 }, { first_outlet_frame: 0 },
      { first_outlet_frame: true }, { observation_seconds: NaN }, { observation_seconds: 2 }].map((patch) =>
      ({ ...outlet, bodies: [{ ...outlet.bodies[0], ...patch }, ...outlet.bodies.slice(1)] }))];
  for (const proof of invalid) {
    const broken = structuredClone(good);
    broken.attempt_quality[0].framing.outlet = proof;
    assert.throws(() => assertNative3dQuality(broken, { seed: 123 }), /3D publication blocked/u);
  }
  for (const patch of [{ contact_model: undefined }, { contact_model: 'old-shrinkwrap' },
    { classification: undefined }, { outside_vertices_moved: undefined },
    { outside_vertices_moved: 1 }, { outside_vertices_moved: false }, { outside_vertices_moved: NaN }]) {
    const broken = structuredClone(good);
    Object.assign(broken.attempt_quality[0].rendered_surface, patch);
    assert.throws(() => assertNative3dQuality(broken, { seed: 123 }), /3D publication blocked/u);
  }
});

test('daily 3D import prefers the latest default-branch render and accepts the cloud scheduler', async () => {
  const workflow = await repositoryFile('.github/workflows/daily-publisher.yml');
  const source = await fs.readFile(workflow, 'utf8');
  const step = source.split("- name: Import today's completed 3D renders")[1].split('- name: Check connected accounts')[0];
  assert.match(step, /DEFAULT_BRANCH:.*github\.event\.repository\.default_branch/u);
  assert.ok(step.includes('-f branch="$DEFAULT_BRANCH"'));
  assert.ok(step.includes('sort_by(.created_at, .run_number) | reverse'));
  assert.ok(step.includes('.event == "schedule" or .event == "workflow_dispatch"'));
  assert.ok(step.includes('manifest.get("date") != sys.argv[2]'));
  assert.ok(step.includes('channel.get("id") == channel_id'));
  assert.ok(step.includes('select(.expired == false)'));
  assert.doesNotMatch(step, /event=schedule|find artifacts\/soft-body-imports.*sort/u);
  assert.ok(step.indexOf('declare -A imported_channels') < step.indexOf('for run_id'));
  assert.ok(step.indexOf('imported_channels[$channel_id]=1') < step.indexOf('if [ "$imported" -eq "$expected" ]'));
});

test('date helpers are deterministic across month boundaries', () => {
  assert.equal(addDays('2026-08-31', 1), '2026-09-01');
  assert.equal(dateInTimeZone(new Date('2026-08-14T23:30:00Z'), 'Europe/Paris'), '2026-08-15');
  assert.equal(isTimeDue('18:30', new Date('2026-08-15T16:30:00Z'), 'Europe/Paris'), true);
});

test('daily plans are stable and keep one fixed game per account', () => {
  const config = { seedNamespace: 'test' };
  const channel = sampleChannel();
  const first = planForDate(config, channel, '2026-08-15');
  const repeated = planForDate(config, channel, '2026-08-15');
  const next = planForDate(config, channel, '2026-08-16');
  assert.deepEqual(first, repeated);
  assert.notEqual(first.seed, next.seed);
  assert.equal(first.renderRequest.game, 'ball-escape');
  assert.deepEqual(first.renderRequest, next.renderRequest);
});

test('configuration is safe by default and refuses unconfirmed public uploads', async (t) => {
  const directory = await temporaryDirectory(t);
  const configPath = path.join(directory, 'publisher.json');
  const base = {
    channels: [{
      id: 'main',
      game: { id: 'ball-escape' },
      youtube: { enabled: false, account: 'default', privacy: 'private' },
      tiktok: { enabled: false },
    }],
  };
  await fs.writeFile(configPath, JSON.stringify(base));
  const config = await readPublisherConfig(configPath, {});
  assert.equal(config.dryRun, true);
  assert.equal(config.channels[0].youtube.enabled, false);
  base.channels[0].youtube = { enabled: true, account: 'default', privacy: 'public' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /confirmPublic/);
  base.channels[0].youtube = { enabled: false, account: 'default', privacy: 'private' };
  base.channels[0].game = { id: 'laser-dodge', difficulty: 200 };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /laser-dodge difficulty/);
  base.channels[0].game = { id: 'ball-escape' };
  base.channels[0].tiktok = { enabled: true, username: 'clipmaker.test', visibility: 'public' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /TikTok public publishing/);
});

test('configuration enforces one game and one assignment per platform account', async (t) => {
  const directory = await temporaryDirectory(t);
  const configPath = path.join(directory, 'publisher.json');
  const base = {
    channels: [{
      id: 'ball-account',
      game: { id: 'ball-escape' },
      youtube: { enabled: true, account: 'main', privacy: 'private' },
      tiktok: { enabled: true, username: 'clipmaker.main', visibility: 'private' },
    }],
  };
  await fs.writeFile(configPath, JSON.stringify(base));
  const config = await readPublisherConfig(configPath, {});
  assert.equal(config.channels[0].game.game, 'ball-escape');

  base.channels[0].game = undefined;
  base.channels[0].rotation = [{ game: 'ball-escape' }, { game: 'laser-dodge' }];
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /exactly one fixed game/);

  base.channels[0].rotation = [{ game: 'ball-escape' }];
  await fs.writeFile(configPath, JSON.stringify(base));
  const legacy = await readPublisherConfig(configPath, {});
  assert.equal(legacy.channels[0].game.game, 'ball-escape');

  base.channels[0].game = { id: 'ball-escape' };
  delete base.channels[0].rotation;
  base.channels.push({
    id: 'laser-account',
    game: { id: 'laser-dodge' },
    youtube: { enabled: true, account: 'MAIN', privacy: 'private' },
    tiktok: { enabled: false },
  });
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /YouTube account.*both/);

  base.channels[1].youtube.enabled = false;
  base.channels[1].tiktok = { enabled: true, username: 'ClipMaker.Main', visibility: 'private' };
  await fs.writeFile(configPath, JSON.stringify(base));
  await assert.rejects(() => readPublisherConfig(configPath, {}), /TikTok account.*both/);

  base.channels[1].enabled = false;
  await fs.writeFile(configPath, JSON.stringify(base));
  const disabledDuplicate = await readPublisherConfig(configPath, {});
  assert.equal(disabledDuplicate.channels.length, 2);
});

test('workflow summary reports the requested operation and active configuration, not a stale job', () => {
  const active = sampleChannel();
  active.id = 'softbody-dvlad';
  active.game = { game: 'soft-body-slide' };
  active.generateTime = '00:07';
  active.publishTime = '18:00';
  active.youtube = { enabled: true, account: 'default', privacy: 'private', confirmPublic: false };
  active.tiktok = { enabled: true, username: 'dvlad', visibility: 'private', confirmPublic: false };
  const summary = buildPublisherSummary({
    operation: 'doctor',
    config: { channels: [active] },
    doctor: {
      ok: true,
      channels: [{
        id: active.id,
        endpoints: { youtube: { ok: true }, tiktok: { ok: true } },
      }],
    },
    status: { jobs: [{
      channelId: 'ball-old',
      date: '2026-08-22',
      status: 'published',
      renderRequest: { game: 'ball-escape' },
      platforms: {
        youtube: {
          enabled: true,
          status: 'published',
          receipt: { id: 'youtube-one', provider: 'youtube-data-api', privacy: 'private' },
        },
        tiktok: { enabled: true, status: 'published', receipt: null },
      },
    }] },
  });
  assert.match(summary, /Operation: `doctor`/u);
  assert.match(summary, /Channel: `softbody-dvlad`/u);
  assert.match(summary, /`soft-body-slide` · génération `00:07` · publication `18:00`/u);
  assert.match(summary, /YouTube default \(private, prêt\)/u);
  assert.match(summary, /TikTok @dvlad \(private, prêt\)/u);
  assert.match(summary, /Latest stored job: `published` · `2026-08-22` · `ball-old` · `ball-escape`/u);
  assert.match(summary, /youtube: `published` · reçu youtube-data-api, private/u);
  assert.match(summary, /tiktok: `published` · aucun reçu enregistré/u);
});

test('a manual dry-run can validate publication without requiring the nightly 3D artifact', async () => {
  const workflowPath = await repositoryFile('.github/workflows/daily-publisher.yml');
  const workflow = await fs.readFile(workflowPath, 'utf8');
  assert.match(
    workflow,
    /Import today's completed 3D renders[\s\S]*steps\.runtime\.outputs\.dry_run == 'false'/u,
  );
  assert.match(workflow, /extra\+=\(--dry-run\)/u);
  assert.match(workflow, /force_youtube:/u);
  assert.match(workflow, /extra\+=\(--force-platform youtube\)/u);
  assert.match(workflow, /force_tiktok:/u);
  assert.match(workflow, /extra\+=\(--force-platform tiktok\)/u);
  assert.match(workflow, /GITHUB_EVENT_NAME.*workflow_dispatch.*MANUAL_DRY_RUN.*true/u);
  assert.match(workflow, /--env YOUTUBE_API_DRY_RUN="\$publisher_dry_run"/u);
  assert.match(workflow, /--env PUBLISHER_DRY_RUN="\$publisher_dry_run"/u);
});

test('cloud YouTube uploads use the OAuth Data API without a persistent browser', async () => {
  const workflowPath = await repositoryFile('.github/workflows/daily-publisher.yml');
  const dockerfilePath = new URL('../../Dockerfile', import.meta.url);
  const [workflow, dockerfile] = await Promise.all([
    fs.readFile(workflowPath, 'utf8'),
    fs.readFile(dockerfilePath, 'utf8'),
  ]);
  assert.match(workflow, /YOUTUBE_OAUTH_ACCOUNTS_B64: \$\{\{ secrets\.YOUTUBE_OAUTH_ACCOUNTS_B64 \}\}/u);
  assert.match(workflow, /--env YOUTUBE_UPLOAD_PROVIDER=youtube-data-api/u);
  assert.match(workflow, /--env YOUTUBE_API_DRY_RUN="\$publisher_dry_run"/u);
  assert.doesNotMatch(workflow, /Xvfb :99/u);
  const ciStage = dockerfile.split('FROM runtime-base AS ci')[1].split('\nFROM ')[0];
  assert.doesNotMatch(ciStage, /xvfb/u);
});

test('every scheduled 3D render reports success or failure with a direct run link', async () => {
  const workflowPath = await repositoryFile('.github/workflows/soft-body-artifact.yml');
  const workflow = await fs.readFile(workflowPath, 'utf8');
  assert.match(workflow, /issues: write/u);
  assert.match(workflow, /always\(\) && github\.event_name == 'schedule'/u);
  assert.match(workflow, /gh issue comment 36/u);
  assert.match(workflow, /Échec du rendu 3D quotidien/u);
  assert.match(workflow, /actions\/runs\/\$\{GITHUB_RUN_ID\}/u);
});

test('missing 3D frame chunks are detected, retried and required before assembly', async () => {
  const workflowPath = await repositoryFile('.github/workflows/soft-body-artifact.yml');
  const workflow = await fs.readFile(workflowPath, 'utf8');
  assert.match(workflow, /continue-on-error: true/u);
  assert.match(workflow, /Find missing native frame chunks/u);
  assert.match(workflow, /f"soft-body-frames-\{frame\['key'\]\}-\{frame\['index'\]\}"/u);
  assert.match(workflow, /needs\.retry_plan\.outputs\.has_missing == 'true'/u);
  assert.match(workflow, /needs\.retry\.result == 'success'/u);
  assert.match(workflow, /Lots manquants détectés/u);
});

test('scheduled 3D renders use short reliable chunks without exceeding GitHub matrix limits', async () => {
  const workflowPath = await repositoryFile('.github/workflows/soft-body-artifact.yml');
  const workflow = await fs.readFile(workflowPath, 'utf8');
  assert.match(workflow, /"samples": 64, "chunk_size": 15/u);
  assert.match(workflow, /if len\(channels\) > 4:[\s\S]*channel\["chunk_size"\] = 30/u);
  assert.match(workflow, /if len\(channels\) > 8:/u);
  assert.equal((workflow.match(/max-parallel: 18/gu) || []).length, 2);
  assert.doesNotMatch(workflow, /max-parallel: 20/u);
  const prepare = workflow.slice(workflow.indexOf('\n  prepare:'), workflow.indexOf('\n  render:'));
  assert.match(prepare, /timeout-minutes: 180/u);
  assert.match(prepare, /--width "\$RENDER_WIDTH" --height "\$RENDER_HEIGHT"/u);
  assert.match(prepare, /--events \/scene\/motion-events.json --build-only/u);
});

test('production 3D assembly rejects a video without the generated audio mix', async () => {
  const workflowPath = await repositoryFile('.github/workflows/soft-body-artifact.yml');
  const workflow = await fs.readFile(workflowPath, 'utf8');
  assert.match(workflow, /stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,sample_rate,channels/u);
  assert.match(workflow, /expected_audio = \("aac", "48000", 2\)/u);
  assert.match(workflow, /29\.9 <= duration <= 30\.1/u);
  assert.match(workflow, /metadata\.get\("music_generated"\) is not True/u);
  assert.match(workflow, /metadata\.get\("sound_pack"\) != "premium-foley"/u);
});

test('TikTok upload uses the verified Studio browser contract and an admin token', async () => {
  const routePath = new URL('../app/api/tiktok/upload/route.ts', import.meta.url);
  const uploaderPath = await repositoryFile('vendor/TiktokAutoUploader/tiktok_uploader/studio-upload.cjs');
  const agentPath = new URL('../../scripts/tiktok-studio-agent.cjs', import.meta.url);
  const [source, uploader, agent] = await Promise.all([
    fs.readFile(routePath, 'utf8'),
    fs.readFile(uploaderPath, 'utf8'),
    fs.readFile(agentPath, 'utf8'),
  ]);
  assert.match(source, /'--users', username/);
  assert.match(source, /'--visibility'/);
  assert.match(source, /x-clipmaker-upload-token/);
  assert.match(source, /parseUploaderReceipt\(stdout, username\)/u);
  assert.match(source, /\^\\d\{12,25\}\$/u);
  assert.match(source, /raw\.verifiedInStudio !== true/u);
  assert.match(source, /platformPostId/u);
  assert.match(uploader, /CLIPMAKER_RECEIPT:/u);
  assert.match(uploader, /tiktok-studio-browser/u);
  assert.match(uploader, /verifiedInStudio: true/u);
  assert.match(uploader, /confirmPost\(page, baseline, responseIds\)/u);
  assert.match(agent, /studio-upload\.cjs/u);
  assert.doesNotMatch(source, /'--user', username/);
});

test('publisher doctor proves that TikTok Studio can load before publishing', async () => {
  const routePath = new URL('../app/api/tiktok/accounts/route.ts', import.meta.url);
  const clientPath = new URL('./api-client.mjs', import.meta.url);
  const agentPath = new URL('../../scripts/tiktok-studio-agent.cjs', import.meta.url);
  const [route, client, agent] = await Promise.all([
    fs.readFile(routePath, 'utf8'),
    fs.readFile(clientPath, 'utf8'),
    fs.readFile(agentPath, 'utf8'),
  ]);
  assert.match(route, /tiktok-studio-agent\.cjs/u);
  assert.match(agent, /studio-upload\.cjs/u);
  assert.match(route, /CLIPMAKER_TIKTOK_DOCTOR:/u);
  assert.match(route, /readyForLiveUpload !== true/u);
  assert.match(client, /\/api\/tiktok\/accounts\?verify=/u);
  assert.match(client, /account\.studioReady === true/u);
});

test('state writes atomically and rejects a concurrent publisher', async (t) => {
  const directory = await temporaryDirectory(t);
  await saveState(directory, { version: 1, updatedAt: null, jobs: [{ id: 'one' }] });
  assert.equal((await loadState(directory)).jobs[0].id, 'one');
  await withStateLock(directory, async () => {
    await assert.rejects(() => withStateLock(directory, async () => {}), /already running/);
  });
});

test('dry-run due planning never creates state or performs network writes', async (t) => {
  const directory = await temporaryDirectory(t);
  const config = {
    dryRun: true,
    timeZone: 'Europe/Paris',
    seedNamespace: 'test',
    stateDir: directory,
    catchupDays: 2,
    retentionDays: 120,
    channels: [sampleChannel()],
  };
  const results = await runDue(config, { now: new Date('2026-08-15T17:00:00Z') });
  assert.equal(results.length, 2);
  assert.equal(results.every((result) => result.dryRun), true);
  assert.deepEqual((await loadState(directory)).jobs, []);
});

test('a native 3D artifact is imported with the deterministic daily seed', async (t) => {
  const directory = await temporaryDirectory(t);
  const channel = sampleChannel();
  channel.id = 'soft-main';
  channel.game = { game: 'soft-body-slide', difficulty: 100, duration: 30, obstacle: 'auto', title: 'HOW SOFT CAN IT GET?' };
  const config = {
    dryRun: false,
    timeZone: 'Europe/Paris',
    seedNamespace: 'test',
    stateDir: directory,
    catchupDays: 2,
    retentionDays: 120,
    channels: [channel],
  };
  const date = '2026-08-15';
  const plan = planForDate(config, channel, date);
  const result = await importRenderedJob(config, {
    date,
    channelId: channel.id,
    seed: plan.seed,
    filename: `soft-body-peg-grid-${plan.seed}.mp4`,
    render: { title: 'HOW SOFT CAN IT GET?', duration: 30, outcome: 'comparison-complete', variantKey: 'peg-grid', raw: native3dEvidence(plan.seed) },
  });
  assert.equal(result.job.render.status, 'ready');
  assert.equal(result.job.render.filename, `soft-body-peg-grid-${plan.seed}.mp4`);
  await assert.rejects(() => importRenderedJob(config, {
    date, channelId: channel.id, seed: plan.seed + 1, filename: `soft-body-peg-grid-${plan.seed + 1}.mp4`, render: {},
  }), /Seed mismatch/u);
  await assert.rejects(() => importRenderedJob(config, {
    date, channelId: channel.id, seed: plan.seed, filename: `soft-body-peg-grid-${plan.seed}.mp4`, render: {},
  }), /3D publication blocked/u);
});

test('a restored 3D ready job cannot upload without valid physics evidence', async (t) => {
  const directory = await temporaryDirectory(t);
  const channel = sampleChannel();
  channel.game = { game: 'soft-body-slide', duration: 30, obstacle: 'auto' };
  channel.youtube.enabled = true;
  const config = { dryRun: false, stateDir: directory, seedNamespace: 'test', channels: [channel] };
  const date = '2026-08-27';
  const plan = planForDate(config, channel, date);
  const state = await loadState(directory);
  state.jobs.push({ ...plan, status: 'ready', render: { status: 'ready', filename: 'old.mp4', game: 'soft-body-slide', raw: {} },
    platforms: { youtube: { status: 'pending', attempts: 0 } } });
  await saveState(directory, state);
  await assert.rejects(() => publishChannel(config, channel, date), /3D publication blocked/u);
  assert.equal((await loadState(directory)).jobs[0].platforms.youtube.attempts, 0);
});

test('an invalid 3D import cannot replace an existing ready video on disk', async (t) => {
  const directory = await temporaryDirectory(t);
  const configDirectory = path.join(directory, 'config');
  const imports = path.join(directory, 'incoming');
  const renders = path.join(directory, 'renders');
  await Promise.all([configDirectory, imports, renders].map((dir) => fs.mkdir(dir)));
  const configPath = path.join(configDirectory, 'publisher.json');
  await fs.writeFile(configPath, JSON.stringify({ seedNamespace: 'test', channels: [{
    id: 'soft-main', game: { id: 'soft-body-slide' },
  }] }));
  const config = await readPublisherConfig(configPath);
  const date = '2026-08-27';
  const plan = planForDate(config, config.channels[0], date);
  const filename = `soft-body-peg-grid-${plan.seed}.mp4`;
  const destination = path.join(renders, filename);
  await fs.writeFile(destination, 'existing validated video');
  await fs.writeFile(path.join(imports, filename), 'invalid replacement');
  const manifest = path.join(imports, 'publisher-import.json');
  await fs.writeFile(manifest, JSON.stringify({ date, channelId: 'soft-main', seed: plan.seed, video: filename, render: {} }));
  const cli = await repositoryFile('web/scripts/publisher.mjs');
  const result = spawnSync(process.execPath, [cli, 'import-3d', '--config', configPath, '--manifest', manifest], { encoding: 'utf8' });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /3D publication blocked/u);
  assert.equal(await fs.readFile(destination, 'utf8'), 'existing validated video');
  assert.doesNotThrow(() => assertNative3dQuality(native3dEvidence(plan.seed), { seed: plan.seed }));
  const valid = { date, channelId: 'soft-main', seed: plan.seed, filename,
    render: { raw: native3dEvidence(plan.seed) } };
  await importRenderedJob(config, valid);
  await fs.writeFile(manifest, JSON.stringify({ ...valid, video: filename }));
  await fs.writeFile(path.join(imports, filename), 'validated replacement');
  const ready = spawnSync(process.execPath, [cli, 'import-3d', '--config', configPath, '--manifest', manifest], { encoding: 'utf8' });
  assert.equal(ready.status, 0, ready.stderr);
  assert.equal(await fs.readFile(destination, 'utf8'), 'validated replacement');
  assert.equal((await fs.readdir(renders)).filter(name => name.startsWith('.import-')).length, 0);
  await fs.writeFile(path.join(imports, filename), 'newer but different film');
  for (const status of ['partial', 'published', 'failed']) {
    const state = await loadState(config.stateDir);
    state.jobs[0].status = status;
    Object.assign(state.jobs[0].platforms.youtube, { status: status === 'failed' ? 'failed' : 'published',
      attempts: 1, receipt: { id: 'immutable-receipt' } });
    await saveState(config.stateDir, state);
    const retry = spawnSync(process.execPath, [cli, 'import-3d', '--config', configPath, '--manifest', manifest], { encoding: 'utf8' });
    assert.equal(retry.status, 0, retry.stderr);
    assert.equal(JSON.parse(retry.stdout).skipped, true);
    assert.equal(await fs.readFile(destination, 'utf8'), 'validated replacement');
    assert.equal((await loadState(config.stateDir)).jobs[0].platforms.youtube.receipt.id, 'immutable-receipt');
  }
  await withStateLock(config.stateDir, async () => {
    const busy = spawnSync(process.execPath, [cli, 'import-3d', '--config', configPath, '--manifest', manifest], { encoding: 'utf8' });
    assert.equal(busy.status, 75, busy.stderr);
    assert.equal(await fs.readFile(destination, 'utf8'), 'validated replacement');
  });
});

test('a partial platform failure retries only the missing upload', async (t) => {
  const directory = await temporaryDirectory(t);
  const calls = { render: 0, youtube: 0, tiktok: 0 };
  const server = http.createServer((request, response) => {
    response.setHeader('content-type', 'application/json');
    if (request.url === '/api/game/render') {
      calls.render += 1;
      response.end(JSON.stringify({
        ok: true,
        filename: 'daily.mp4',
        title: 'Can It Escape?',
        youtubeTitle: 'Can It Escape? #shorts',
        caption: 'Can it escape? #satisfying',
        tags: ['#satisfying'],
        game: 'ball-escape',
        duration: 15,
        outcome: 'escaped',
      }));
      return;
    }
    if (request.url === '/api/youtube/upload') {
      calls.youtube += 1;
      response.end(JSON.stringify({
        ok: true,
        account: 'default',
        upload: {
          provider: 'youtube-data-api',
          platformPostId: `youtube-${calls.youtube}`,
          releaseUrl: `https://youtube.com/shorts/youtube-${calls.youtube}`,
          raw: { privacy: 'private' },
        },
      }));
      return;
    }
    if (request.url === '/api/tiktok/upload') {
      calls.tiktok += 1;
      if (calls.tiktok === 1) {
        response.statusCode = 503;
        response.end(JSON.stringify({ ok: false, error: 'temporary TikTok failure' }));
      } else {
        response.end(JSON.stringify({
          ok: true,
          upload: {
            provider: 'tiktok-web-upload',
            platformPostId: 'tiktok-one',
            raw: { privacy: 'private' },
          },
        }));
      }
      return;
    }
    response.statusCode = 404;
    response.end(JSON.stringify({ ok: false, error: 'not found' }));
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const address = server.address();
  assert(address && typeof address === 'object');

  const channel = sampleChannel();
  channel.youtube.enabled = true;
  channel.tiktok = {
    enabled: true,
    username: 'clipmaker.test',
    musicId: null,
    visibility: 'private',
    confirmPublic: false,
  };
  const config = {
    dryRun: false,
    baseUrl: `http://127.0.0.1:${address.port}`,
    requestTimeoutMinutes: 1,
    timeZone: 'Europe/Paris',
    seedNamespace: 'test',
    stateDir: directory,
    catchupDays: 2,
    retentionDays: 120,
    channels: [channel],
  };
  const date = '2026-08-15';

  await generateChannel(config, channel, date);
  const repeated = await generateChannel(config, channel, date);
  assert.equal(repeated.skipped, true);
  assert.equal(calls.render, 1);

  await assert.rejects(() => publishChannel(config, channel, date), /temporary TikTok failure/);
  let job = (await loadState(directory)).jobs[0];
  assert.equal(job.status, 'partial');
  assert.equal(job.platforms.youtube.status, 'published');
  assert.equal(job.platforms.tiktok.status, 'failed');
  assert.equal(job.platforms.youtube.receipt.id, 'youtube-1');
  assert.equal(job.platforms.youtube.receipt.privacy, 'private');

  await publishChannel(config, channel, date);
  job = (await loadState(directory)).jobs[0];
  assert.equal(job.status, 'published');
  assert.equal(calls.youtube, 1);
  assert.equal(calls.tiktok, 2);
  assert.equal(job.platforms.tiktok.receipt.id, 'tiktok-one');
  assert.equal(job.platforms.tiktok.receipt.provider, 'tiktok-web-upload');
  assert.equal(job.platforms.tiktok.receipt.privacy, 'private');

  await publishChannel(config, channel, date, { forcePlatforms: ['youtube'] });
  job = (await loadState(directory)).jobs[0];
  assert.equal(job.status, 'published');
  assert.equal(job.platforms.youtube.receipt.id, 'youtube-2');
  assert.equal(calls.youtube, 2);
  assert.equal(calls.tiktok, 2);
  await assert.rejects(
    () => publishChannel(config, { ...channel, youtube: { ...channel.youtube, enabled: false } }, date, {
      forcePlatforms: ['youtube'],
    }),
    /Cannot force disabled platform youtube/u,
  );
});
