const SPECIMENS = {
  'moving-slide': 1,
  'stair-cascade': 3,
  'v-stairs': 2,
  'peg-grid': 2,
  'pipe-bend': 1,
  'twin-gears': 1,
  'compression-ring': 1,
};

// Recheck persisted/imported evidence at the upload boundary too. A ready MP4
// from an older renderer must not bypass today's physics checks.
export function assertNative3dQuality(metadata, { seed, duration = 30, obstacle = 'auto' }) {
  const fail = () => { throw new Error('3D publication blocked: missing, incomplete or failed native physics preflight. Regenerate this video.'); };
  const frames = metadata?.frames;
  const stages = metadata?.softness_stages;
  const reports = metadata?.attempt_quality;
  const specimens = SPECIMENS[metadata?.variant_obstacle];
  if (metadata?.physics_preflight !== 'passed' || metadata?.seed !== seed
    || metadata?.game !== 'soft-body-slide' || !specimens
    || (obstacle !== 'auto' && metadata.variant_obstacle !== obstacle)
    || metadata.render_width !== 1080 || metadata.render_height !== 1920
    || metadata.render_fps !== 30 || metadata.output_fps !== 30
    || !Number.isInteger(frames) || frames <= 0 || frames !== Math.round(duration * 30)
    || metadata.duration !== duration
    || !Array.isArray(stages) || stages.length !== 5
    || stages.some((softness) => !Number.isInteger(softness) || softness < 0 || softness > 100)
    || !Array.isArray(reports) || !reports.length) fail();

  const trials = new Map();
  for (const report of reports) {
    const { stage, softness, attempt, body, start_frame: start, end_frame: end } = report || {};
    if (!Number.isInteger(stage) || stage < 1 || stage > stages.length || softness !== stages[stage - 1]
      || !Number.isInteger(attempt) || attempt < 1 || attempt > 2
      || !Number.isInteger(body) || body < 1 || body > specimens
      || !Number.isInteger(start) || !Number.isInteger(end) || start < 1 || end < start || end > frames
      || !Array.isArray(report.issues) || report.issues.length
      || report.surface?.inside_contacts !== 0) fail();
    const renderedSurface = report.rendered_surface;
    if (renderedSurface?.frames_checked !== end - start + 1
      || !Number.isInteger(renderedSurface?.vertices_checked) || renderedSurface.vertices_checked <= 0
      || renderedSurface.subdivision !== 3 || !Array.isArray(renderedSurface.issues) || renderedSurface.issues.length
      || !Number.isFinite(renderedSurface.maximum_penetration)
      || renderedSurface.maximum_penetration < 0 || renderedSurface.maximum_penetration > 0.003
      || !Number.isFinite(renderedSurface.maximum_correction)
      || renderedSurface.maximum_correction < 0 || renderedSurface.maximum_correction > 0.08) fail();
    const framing = report.framing;
    if (framing?.frames_checked !== end - start + 1 || !Array.isArray(framing?.issues) || framing.issues.length
      || !Number.isFinite(framing.maximum_empty_seconds) || framing.maximum_empty_seconds < 0 || framing.maximum_empty_seconds > 1
      || !Number.isFinite(framing.maximum_side_exit_seconds) || framing.maximum_side_exit_seconds < 0 || framing.maximum_side_exit_seconds > 0.5) fail();
    if (metadata.variant_obstacle === 'stair-cascade') {
      const outlet = framing.outlet;
      if (outlet?.minimum_observation_seconds !== 0.35
        || !Array.isArray(outlet?.issues) || outlet.issues.length
        || !Array.isArray(outlet?.bodies) || outlet.bodies.length !== 3) fail();
      const ids = new Set();
      for (const observation of outlet.bodies) {
        const { body: id, first_outlet_frame: first, observation_seconds: seconds, observed } = observation || {};
        if (!Number.isInteger(id) || id < 1 || id > 3 || ids.has(id) || observed !== true
          || !Number.isInteger(first) || first < 1 || first > framing.frames_checked - Math.ceil(0.35 * 30)
          || !Number.isFinite(seconds) || Math.abs(seconds - (framing.frames_checked - first) / 30) > 0.000051) fail();
        ids.add(id);
      }
    }
    if (specimens > 1 && (report.inter_body_contact?.frames_checked !== end - start + 1
      || !Array.isArray(report.inter_body_contact?.issues) || report.inter_body_contact.issues.length
      || !Number.isFinite(report.inter_body_contact.maximum_penetration)
      || report.inter_body_contact.maximum_penetration < 0
      || report.inter_body_contact.maximum_penetration > 0.008
      || (report.inter_body_contact.spine_inside_contacts !== undefined
        && report.inter_body_contact.spine_inside_contacts !== 0))) fail();
    const key = `${stage}:${attempt}`;
    const trial = trials.get(key) || { stage, attempt, start, end, bodies: new Set() };
    if (trial.start !== start || trial.end !== end || trial.bodies.has(body)) fail();
    trial.bodies.add(body);
    trials.set(key, trial);
  }
  let nextFrame = 1;
  let lastStage = 0;
  let lastAttempt = 0;
  for (const trial of [...trials.values()].sort((a, b) => a.start - b.start)) {
    if (trial.start !== nextFrame || trial.bodies.size !== specimens) fail();
    if (trial.stage === lastStage) {
      if (trial.attempt !== lastAttempt + 1) fail();
    } else if (trial.stage !== lastStage + 1 || trial.attempt !== 1) fail();
    nextFrame = trial.end + 1;
    lastStage = trial.stage;
    lastAttempt = trial.attempt;
  }
  if (nextFrame !== frames + 1 || lastStage !== stages.length) fail();
}
