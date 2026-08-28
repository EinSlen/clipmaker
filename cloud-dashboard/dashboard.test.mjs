import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const root = new URL('./', import.meta.url);

async function source(name) {
  return fs.readFile(new URL(name, root), 'utf8');
}

test('the public dashboard exposes every daily stage and an explicit mobile navigation', async () => {
  const html = await source('index.html');
  const css = await source('styles.css');
  for (const label of ['Accueil', 'Actions', 'Comptes', 'Test 3D', 'Historique']) {
    assert.match(html, new RegExp(`data-mobile-label="${label}"`, 'u'));
  }
  assert.match(css, /content:\s*attr\(data-mobile-label\)/u);
  assert.match(css, /\.nav-link::after\s*\{[^}]*display:\s*block/u);
  assert.doesNotMatch(css, /main\s*\{[^}]*100vw/u);
  assert.match(html, /<time>00:07<\/time>[\s\S]*Rendu 3D/u);
  assert.match(html, /<time>00:37<\/time>[\s\S]*Rendus 2D/u);
  assert.match(html, /<time>18:00<\/time>[\s\S]*Publication Cloudflare/u);
  assert.match(html, /<time>≈18:02<\/time>[\s\S]*Notification/u);
  assert.match(html, /<time>18:07<\/time>[\s\S]*Secours GitHub/u);
  assert.match(html, /toutes les 5 minutes/u);
});

test('the public dashboard exposes the persisted Cloudflare watchdog heartbeat', async () => {
  const html = await source('index.html');
  const app = await source('app.js');
  assert.match(html, /id="watchdog-status"/u);
  assert.match(html, /id="watchdog-time"/u);
  assert.match(app, /fetch\(`\$\{CONTROL_API\}\/health`/u);
  assert.match(app, /Aucun doublon/u);
  assert.match(app, /loadWatchdog\(\)/u);
});

test('account setup offers creation, private connection and local fallback links', async () => {
  const html = await source('index.html');
  assert.match(html, /https:\/\/www\.tiktok\.com\/signup/u);
  assert.match(html, /https:\/\/accounts\.google\.com\/signup/u);
  assert.match(html, /https:\/\/codespaces\.new\/EinSlen\/clipmaker\?quickstart=1/u);
  assert.match(html, /Studio local \(si démarré\)/u);
  assert.match(html, /Créer puis connecter un nouveau compte/u);
});

test('the meta CSP contains only directives that browsers enforce there', async () => {
  const html = await source('index.html');
  assert.match(html, /object-src 'none'/u);
  assert.doesNotMatch(html, /frame-ancestors/u);
});

test('the one-account-one-game editor and all public destinations remain present', async () => {
  const html = await source('index.html');
  const app = await source('app.js');
  for (const id of ['overview', 'commands', 'configuration', 'three-d', 'runs']) {
    assert.match(html, new RegExp(`id="${id}"`, 'u'));
  }
  assert.match(html, /Un compte, un jeu/u);
  assert.match(app, /label\.textContent = 'JEU DE CE COMPTE'/u);
  assert.match(app, /field\('Jeu sélectionné'/u);
  assert.match(app, /Maximum : 8 comptes par dépôt/u);
  assert.match(app, /Je confirme la publication/u);
  assert.match(html, /issues\/36/u);
  assert.match(html, /actions\/workflows\/soft-body-artifact\.yml/u);
});

test('every game has a real gameplay preview in the account editor', async () => {
  const app = await source('app.js');
  const css = await source('styles.css');
  const games = ['ball-escape', 'shape-tunnel', 'laser-dodge', 'boss-battle', 'soft-body-slide'];
  for (const game of games) {
    assert.match(app, new RegExp(`assets/games/${game}\\.webp`, 'u'));
    const stat = await fs.stat(new URL(`assets/games/${game}.webp`, root));
    assert.ok(stat.size > 8_000, `${game} preview should contain a real rendered frame`);
  }
  assert.match(app, /renderGamePicker\(channel\)/u);
  assert.match(app, /Aperçu gameplay/u);
  assert.match(css, /\.game-picker-list/u);
  assert.match(css, /\.game-choice\.selected/u);
  assert.match(app, /list\.querySelector\('\.game-choice\.selected'\)/u);
  assert.match(app, /list\.scrollLeft \+=/u);
});

test('current assignment and last published game are presented separately', async () => {
  const html = await source('index.html');
  const app = await source('app.js');
  assert.match(html, /Configuration actuelle/u);
  assert.match(html, /Dernière publication/u);
  assert.match(app, /Jeu assigné/u);
  assert.match(app, /Latest stored job/u);
  assert.match(app, /latestPublishedDetail/u);
  assert.match(html, /id="latest-published-visibility"/u);
  assert.match(app, /Privée · aucune vue publique/u);
  assert.match(app, /Visible publiquement/u);
  assert.match(app, /formatDay\(`\$\{published\[1\]\}T12:00:00Z`\)/u);
  assert.doesNotMatch(app, /formatDate\(`\$\{published\[1\]\}T12:00:00Z`\)/u);
});

test('manual 3D renders default to the reliable 15-frame chunks', async () => {
  const html = await source('index.html');
  assert.match(html, /<option value="15" selected>15 images · recommandé<\/option>/u);
  assert.doesNotMatch(html, /<option value="30" selected>/u);
});

test('generation explains saved assignments and shows the server-selected pipeline', async () => {
  const html = await source('index.html');
  const app = await source('app.js');
  assert.match(html, /vidéos 2D\/3D du planning sauvegardé/u);
  assert.match(app, /comptes et jeux du planning sauvegardé/u);
  assert.match(app, /notify\(result\.message \|\| successMessage\)/u);
});

test('changing a game explains regeneration and the in-flight publication boundary', async () => {
  const html = await source('index.html');
  assert.match(html, /id="selection-help"/u);
  assert.match(html, /Sauvegarde, puis lance « Générer maintenant »/u);
  assert.match(html, /Si un envoi a déjà commencé/u);
  assert.match(html, /le nouveau choix servira le lendemain/u);
});

test('cloud activity shows an ongoing 3D render instead of a successful doctor', async () => {
  const app = await source('app.js');
  const functions = app.slice(app.indexOf('  function runLabel('), app.indexOf('  function renderRuns('));
  const activity = vm.runInNewContext(`${functions}; runActivity`);
  const doctor = { id: 1, status: 'completed', conclusion: 'success', display_title: 'ClipMaker · doctor',
    created_at: '2026-08-28T14:00:00Z', path: '.github/workflows/daily-publisher.yml' };
  const render = { id: 2, status: 'in_progress', created_at: '2026-08-28T13:00:00Z',
    path: '.github/workflows/soft-body-artifact.yml' };
  const current = activity([doctor, render]);
  assert.equal(current.run.id, 2);
  assert.equal(current.label, 'En cours');
  assert.equal(current.operation, 'Rendu 3D');
  assert.equal(activity([doctor]).operation, 'Vérification des comptes');
  assert.equal(activity([{ ...doctor, display_title: 'ClipMaker · publish 18:00' }]).operation, 'Publication');
  assert.equal(activity([{ ...doctor, display_title: 'ClipMaker · generate' }]).operation, 'Génération');
  assert.equal(activity([render, doctor, { ...render, status: 'completed', conclusion: 'failure',
    created_at: '2026-08-28T15:00:00Z' }]).label, 'En cours');
  assert.equal(activity([{ ...render, status: 'completed', conclusion: 'failure' }]).label, 'Échec');
  assert.equal(activity([]), null);
  assert.match(app, /runs\?per_page=5&branch=main/u);
  assert.match(app, /runs\?per_page=3&branch=main/u);
  const html = await source('index.html');
  assert.match(html, /Activité cloud/u);
  assert.doesNotMatch(html, /Dernier cron|rattraper automatiquement toute panne/u);
  assert.match(html, /L’envoi dépend d’un rendu validé/u);
});
