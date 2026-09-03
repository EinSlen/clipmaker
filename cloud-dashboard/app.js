(() => {
  'use strict';

  const OWNER = 'EinSlen';
  const REPO = 'clipmaker';
  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
  const CONTROL_API = 'https://clipmaker-cloud-control.einslen.workers.dev';
  const SESSION_KEY = 'clipmaker-cloud-session';
  const LEGACY_TOKEN_KEY = 'clipmaker-github-token';
  const elements = {
    connect: document.querySelector('#connect-github'),
    disconnect: document.querySelector('#disconnect-github'),
    authState: document.querySelector('#auth-state'),
    refresh: document.querySelector('#refresh-all'),
    latestStatus: document.querySelector('#latest-status'),
    latestTime: document.querySelector('#latest-time'),
    latestChannel: document.querySelector('#latest-channel'),
    latestOperation: document.querySelector('#latest-operation'),
    latestPublished: document.querySelector('#latest-published'),
    latestPublishedDetail: document.querySelector('#latest-published-detail'),
    latestPublishedVisibility: document.querySelector('#latest-published-visibility'),
    watchdogStatus: document.querySelector('#watchdog-status'),
    watchdogTime: document.querySelector('#watchdog-time'),
    runs: document.querySelector('#runs-list'),
    toast: document.querySelector('#toast'),
    form3d: document.querySelector('#three-d-form'),
    configState: document.querySelector('#config-state'),
    sessionsState: document.querySelector('#sessions-state'),
    globalMode: document.querySelector('#global-mode'),
    channelList: document.querySelector('#channel-list'),
    addChannel: document.querySelector('#add-channel'),
    saveConfig: document.querySelector('#save-config'),
    reloadConfig: document.querySelector('#reload-config'),
  };

  const GAMES = [
    { id: 'ball-escape', name: 'Ball Escape', description: 'Anneaux et gravité', preview: 'assets/games/ball-escape.webp', difficulty: 14, duration: 15, title: 'CAN IT ESCAPE?', musicMode: 'hit-reveal' },
    { id: 'shape-tunnel', name: 'Organic Escape', description: 'Couches organiques', preview: 'assets/games/shape-tunnel.webp', difficulty: 200, duration: 15, title: 'HOW MANY LAYERS?', musicMode: 'continuous' },
    { id: 'laser-dodge', name: 'Laser Dodge', description: 'Esquive de lasers', preview: 'assets/games/laser-dodge.webp', difficulty: 24, duration: 15, title: 'CAN IT DODGE THEM ALL?', musicMode: 'hit-reveal' },
    { id: 'boss-battle', name: 'Boss Battle', description: 'Combat physique', preview: 'assets/games/boss-battle.webp', difficulty: 300, duration: 15, title: 'WHO WILL WIN?', musicMode: 'hit-reveal' },
    { id: 'soft-body-slide', name: 'Souplesse 3D', description: 'Simulation Blender', preview: 'assets/games/soft-body-slide.webp', difficulty: 100, duration: 30, title: 'HOW SOFT CAN IT GET?', musicMode: 'continuous' },
    { id: 'story-comments', name: 'Histoire pilotée', description: 'Short drama, la suite vient des commentaires', preview: 'assets/games/story-comments.webp', difficulty: 60, duration: 60, title: 'TU CHOISIS LA SUITE', musicMode: 'continuous' },
  ];
  const OBSTACLES = [
    ['auto', 'Automatique — sélection principale'], ['moving-slide', 'Rampe mobile'],
    ['stair-cascade', 'Cascade d’escaliers'], ['v-stairs', 'Barres en V'],
    ['pipe-bend', 'Tube courbé — expérimental'], ['peg-grid', 'Grille de barres'],
    ['twin-gears', 'Double engrenage — expérimental'], ['compression-ring', 'Rouleaux — expérimental'],
  ];
  let publisherConfig = null;
  let accountCatalog = { tiktok: [], youtube: [] };

  function readStoredSession() {
    try {
      return localStorage.getItem(SESSION_KEY) || '';
    } catch {
      return '';
    }
  }

  function saveSession(value) {
    try {
      localStorage.setItem(SESSION_KEY, value);
    } catch {
      throw new Error('Le navigateur bloque le stockage de la connexion GitHub.');
    }
  }

  function forgetSession() {
    try {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(LEGACY_TOKEN_KEY);
    } catch {
      // The in-memory session is still cleared below.
    }
    sessionStorage.removeItem(LEGACY_TOKEN_KEY);
  }

  function acceptOAuthCallback() {
    const parameters = new URLSearchParams(window.location.hash.slice(1));
    const received = parameters.get('github-session') || '';
    if (!received) return '';
    window.history.replaceState({}, document.title, `${window.location.pathname}${window.location.search}`);
    if (!/^v1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/u.test(received)) return '';
    saveSession(received);
    return received;
  }

  let session = acceptOAuthCallback() || readStoredSession();
  let toastTimer;

  function headers() {
    return {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2026-03-10',
    };
  }

  function notify(message, error = false) {
    clearTimeout(toastTimer);
    elements.toast.textContent = message;
    elements.toast.classList.toggle('error', error);
    elements.toast.classList.add('show');
    toastTimer = setTimeout(() => elements.toast.classList.remove('show'), 5200);
  }

  async function github(path, options = {}) {
    const response = await fetch(path.startsWith('http') ? path : `${API}${path}`, {
      ...options,
      headers: { ...headers(), ...(options.headers || {}) },
    });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || `GitHub a répondu ${response.status}.`);
    return payload;
  }

  async function control(path, options = {}) {
    if (!session) throw new Error('Connecte-toi avec GitHub pour utiliser cette commande.');
    const response = await fetch(`${CONTROL_API}${path}`, {
      ...options,
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${session}`,
        ...(options.headers || {}),
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (payload.session) {
      session = payload.session;
      saveSession(session);
    }
    if (!response.ok) throw new Error(payload.error || `Contrôle Cloud indisponible (${response.status}).`);
    return payload;
  }

  function lockCommands() {
    document.querySelectorAll('.requires-token').forEach((button) => {
      button.disabled = !session;
      button.title = session ? '' : 'Connecte-toi avec GitHub pour utiliser cette commande.';
    });
    elements.connect.hidden = Boolean(session);
    elements.disconnect.hidden = !session;
  }

  function optionNode(value, label, selected) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    option.selected = value === selected;
    return option;
  }

  function selectNode(entries, selected, onChange) {
    const select = document.createElement('select');
    select.replaceChildren(...entries.map(([value, label]) => optionNode(value, label, selected)));
    select.addEventListener('change', () => onChange(select.value));
    return select;
  }

  function inputNode(value, type, onChange) {
    const input = document.createElement('input');
    input.type = type;
    input.value = value ?? '';
    input.addEventListener('input', () => onChange(type === 'number' ? Number(input.value) : input.value));
    return input;
  }

  function field(label, control, className = '') {
    const wrapper = document.createElement('label');
    if (className) wrapper.className = className;
    const caption = document.createElement('span');
    caption.textContent = label;
    wrapper.append(caption, control);
    return wrapper;
  }

  function platformReady(platform, account) {
    if (!account) return false;
    const entries = accountCatalog[platform] || [];
    return entries.some((item) => String(item.username || item.id).toLowerCase() === String(account).toLowerCase() && item.ready);
  }

  function accountEntries(platform, current) {
    const source = accountCatalog[platform] || [];
    const values = source.map((item) => platform === 'tiktok'
      ? [item.username, `@${item.username}${item.ready ? ' · prête' : ' · à reconnecter'}`]
      : [item.id, `${item.label || item.id}${item.ready ? ' · OAuth prêt' : ' · OAuth requis'}`]);
    if (current && !values.some(([value]) => value === current)) values.unshift([current, `${current} · session inconnue`]);
    return [['', 'Choisir un compte'], ...values];
  }

  function renderPlatform(channel, platform) {
    const settings = channel[platform];
    const isTiktok = platform === 'tiktok';
    const accountKey = isTiktok ? 'username' : 'account';
    const privacyKey = isTiktok ? 'visibility' : 'privacy';
    const box = document.createElement('div');
    box.className = 'platform-box';
    const title = document.createElement('div');
    title.className = 'platform-title';
    const toggle = document.createElement('label');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = settings.enabled;
    checkbox.addEventListener('change', () => { settings.enabled = checkbox.checked; renderChannels(); });
    const name = document.createElement('span');
    name.textContent = isTiktok ? 'TikTok' : 'YouTube Shorts';
    toggle.append(checkbox, name);
    const ready = document.createElement('span');
    const isReady = platformReady(platform, settings[accountKey]);
    ready.className = `platform-ready${isReady ? ' ready' : ''}`;
    ready.textContent = isReady ? (isTiktok ? 'Session prête' : 'OAuth prêt') : (isTiktok ? 'Session requise' : 'OAuth requis');
    title.append(toggle, ready);
    box.append(title);

    const account = selectNode(accountEntries(platform, settings[accountKey]), settings[accountKey] || '', (value) => {
      settings[accountKey] = value || (isTiktok ? null : 'default');
      renderChannels();
    });
    account.disabled = !settings.enabled;
    box.append(field(isTiktok ? 'Compte TikTok' : 'Chaîne YouTube', account));
    const privacyValues = isTiktok
      ? [['private', 'Privée'], ['public', 'Publique']]
      : [['private', 'Privée'], ['unlisted', 'Non répertoriée'], ['public', 'Publique']];
    const privacy = selectNode(privacyValues, settings[privacyKey], (value) => {
      settings[privacyKey] = value;
      settings.confirmPublic = false;
      renderChannels();
    });
    privacy.disabled = !settings.enabled;
    box.append(field('Visibilité', privacy));
    if (settings.enabled && settings[privacyKey] === 'public') {
      const confirmation = document.createElement('label');
      confirmation.className = 'public-confirm';
      const confirm = document.createElement('input');
      confirm.type = 'checkbox';
      confirm.checked = Boolean(settings.confirmPublic);
      confirm.addEventListener('change', () => { settings.confirmPublic = confirm.checked; });
      const copy = document.createElement('span');
      copy.textContent = `Je confirme la publication ${isTiktok ? 'TikTok' : 'YouTube'} publique`;
      confirmation.append(confirm, copy);
      box.append(confirmation);
    }
    return box;
  }

  function assignGame(channel, value) {
    const definition = GAMES.find((item) => item.id === value) || GAMES[0];
    channel.game = {
      ...channel.game,
      id: definition.id,
      difficulty: definition.difficulty,
      duration: definition.duration,
      title: definition.title,
      musicMode: definition.musicMode,
    };
    if (definition.id === 'soft-body-slide') channel.game.obstacle = 'auto';
    else { delete channel.game.obstacle; delete channel.game.musicProfile; }
    if (definition.id === 'story-comments') {
      channel.game.series = channel.game.series || channel.id;
      if (channel.tiktok?.username) channel.game.tiktokUser = channel.tiktok.username;
    } else { delete channel.game.series; delete channel.game.tiktokUser; delete channel.game.storyTheme; }
    renderChannels();
  }

  function renderGamePicker(channel) {
    const picker = document.createElement('section');
    picker.className = 'game-picker';
    const heading = document.createElement('div');
    heading.className = 'game-picker-heading';
    const copy = document.createElement('div');
    const label = document.createElement('span');
    label.textContent = 'JEU DE CE COMPTE';
    const selected = GAMES.find((item) => item.id === channel.game.id) || GAMES[0];
    const current = document.createElement('strong');
    current.textContent = `${selected.name} · ${selected.description}`;
    copy.append(label, current);
    const hint = document.createElement('small');
    hint.textContent = 'Clique sur un aperçu pour changer le rendu quotidien.';
    heading.append(copy, hint);

    const list = document.createElement('div');
    list.className = 'game-picker-list';
    list.append(...GAMES.map((game) => {
      const button = document.createElement('button');
      const active = game.id === channel.game.id;
      button.type = 'button';
      button.className = `game-choice${active ? ' selected' : ''}`;
      button.setAttribute('aria-pressed', String(active));
      button.setAttribute('aria-label', `Choisir ${game.name}`);
      button.addEventListener('click', () => assignGame(channel, game.id));
      const image = document.createElement('img');
      image.src = game.preview;
      image.alt = `Aperçu gameplay ${game.name}`;
      image.loading = 'lazy';
      image.width = 240;
      image.height = 427;
      const caption = document.createElement('span');
      const name = document.createElement('strong');
      name.textContent = game.name;
      const description = document.createElement('small');
      description.textContent = game.description;
      caption.append(name, description);
      button.append(image, caption);
      return button;
    }));
    picker.append(heading, list);
    return picker;
  }

  function renderChannel(channel, index) {
    const card = document.createElement('article');
    card.className = 'channel-card';
    const head = document.createElement('div');
    head.className = 'channel-head';
    const title = document.createElement('div');
    title.className = 'channel-title';
    const enabled = document.createElement('input');
    enabled.type = 'checkbox';
    enabled.checked = channel.enabled;
    enabled.setAttribute('aria-label', `Activer ${channel.id}`);
    enabled.addEventListener('change', () => { channel.enabled = enabled.checked; renderChannels(); });
    const titleCopy = document.createElement('span');
    const game = GAMES.find((item) => item.id === channel.game.id) || GAMES[0];
    const strong = document.createElement('strong');
    strong.textContent = channel.id;
    const small = document.createElement('small');
    small.textContent = `${game.name} · publication ${channel.publishTime}`;
    titleCopy.append(strong, small);
    title.append(enabled, titleCopy);
    const remove = document.createElement('button');
    remove.className = 'remove-channel';
    remove.type = 'button';
    remove.textContent = '×';
    remove.setAttribute('aria-label', `Supprimer ${channel.id}`);
    remove.disabled = publisherConfig.channels.length === 1;
    remove.addEventListener('click', () => {
      if (publisherConfig.channels.length > 1 && window.confirm(`Supprimer le canal ${channel.id} ?`)) {
        publisherConfig.channels.splice(index, 1);
        renderChannels();
      }
    });
    head.append(title, remove);
    card.append(head, renderGamePicker(channel));

    const fields = document.createElement('div');
    fields.className = 'channel-fields';
    fields.append(field('Identifiant', inputNode(channel.id, 'text', (value) => { channel.id = String(value).toLowerCase(); })));
    fields.append(field('Jeu sélectionné', selectNode(GAMES.map((item) => [item.id, item.name]), channel.game.id, (value) => assignGame(channel, value))));
    fields.append(field('Génération', inputNode(channel.generateTime, 'time', (value) => { channel.generateTime = value; })));
    fields.append(field('Publication', inputNode(channel.publishTime, 'time', (value) => { channel.publishTime = value; })));
    fields.append(field('Accroche vidéo (anglais)', inputNode(channel.game.title, 'text', (value) => { channel.game.title = value; }), 'field-span-2'));
    fields.append(field('Description de la publication', selectNode([
      ['auto', 'Automatique — suit la voix choisie'], ['melancholic', 'Mélancolique — 48 phrases anglaises'],
      ['revenge', 'Revenge — 24 phrases anglaises'], ['gameplay', 'Classique — description du jeu'],
    ], channel.captionStyle || 'auto', (value) => { channel.captionStyle = value; }), 'field-span-2'));
    const captionNote = document.createElement('p'); captionNote.className = 'field-span-2';
    captionNote.textContent = 'Une description différente chaque jour, conservée lors des relances. Les crédits audio restent inclus. Exemple : “some feelings outlive the goodbye.”';
    fields.append(captionNote);
    if (channel.game.id === 'story-comments') {
      fields.append(field('Identifiant de la série', inputNode(channel.game.series || channel.id, 'text', (value) => { channel.game.series = value.trim() || channel.id; }), 'field-span-2'));
      fields.append(field('Thème de départ (utilisé une seule fois, au premier épisode)', inputNode(channel.game.storyTheme || '', 'text', (value) => { channel.game.storyTheme = value.trim(); }), 'field-span-2'));
      const storyNote = document.createElement('p'); storyNote.className = 'field-span-2';
      storyNote.textContent = 'Un épisode par jour en français, casting fixe, cliffhanger final. Chaque épisode reprend le commentaire le plus pertinent de la veille et crédite son auteur à l’écran. Sans commentaire exploitable, l’histoire continue seule.';
      fields.append(storyNote);
    }
    if (channel.game.id === 'soft-body-slide') {
      fields.append(field('Obstacle 3D', selectNode(OBSTACLES, channel.game.obstacle || 'auto', (value) => { channel.game.obstacle = value; }), 'field-span-2'));
      fields.append(field('Voix et ambiance', selectNode([
        ['edit-auto', 'Voix d’edit — mix aléatoire'],
        ['edit-sad', 'Voix d’edit — triste'],
        ['edit-revenge', 'Voix d’edit — revenge'],
        ['auto', 'Chansons NCS — mix (option historique)'],
        ['revenge', 'Chansons NCS — puissant'],
        ['sad-english', 'Chansons NCS — mélancolique'],
        ['original', 'Ambiance originale — sans paroles'],
      ], channel.game.musicProfile || 'original', (value) => { channel.game.musicProfile = value; }), 'field-span-2'));
      const musicNote = document.createElement('p');
      musicNote.className = 'field-span-2';
      musicNote.textContent = 'Voix d’edit : extraits parlés complets de la bibliothèque privée. Un choix par jour et par compte, stable en cas de relance. Une bibliothèque vide ne remplace jamais une voix par une chanson.';
      fields.append(musicNote);
      const libraryLink = document.createElement('a');
      libraryLink.href = '#audio-library';
      libraryLink.textContent = 'Importer et écouter mes voix d’edit';
      fields.append(libraryLink);
    } else {
      fields.append(field('Durée', selectNode([['15', '15 secondes'], ['30', '30 secondes'], ['45', '45 secondes'], ['60', '60 secondes']], String(channel.game.duration), (value) => { channel.game.duration = Number(value); })));
      fields.append(field('Niveau', inputNode(channel.game.difficulty, 'number', (value) => { channel.game.difficulty = value; })));
    }
    const platforms = document.createElement('div');
    platforms.className = 'platforms-grid';
    platforms.append(renderPlatform(channel, 'tiktok'), renderPlatform(channel, 'youtube'));
    fields.append(platforms);
    card.append(fields);
    return card;
  }

  function renderChannels() {
    if (!publisherConfig) {
      elements.channelList.replaceChildren();
      const empty = document.createElement('div');
      empty.className = 'channel-empty';
      empty.textContent = 'Connecte-toi avec GitHub pour charger les comptes et les jeux.';
      elements.channelList.append(empty);
      return;
    }
    elements.globalMode.value = publisherConfig.dryRun ? 'test' : 'live';
    elements.channelList.replaceChildren(...publisherConfig.channels.map(renderChannel));
    // On narrow screens, keep the assigned game visible instead of always
    // showing the first thumbnail (which may be a completely different game).
    requestAnimationFrame(() => {
      elements.channelList.querySelectorAll('.game-picker-list').forEach((list) => {
        const selected = list.querySelector('.game-choice.selected');
        if (!selected) return;
        const bounds = list.getBoundingClientRect();
        const choice = selected.getBoundingClientRect();
        if (choice.left < bounds.left || choice.right > bounds.right) {
          list.scrollLeft += choice.left - bounds.left - (list.clientWidth - choice.width) / 2;
        }
      });
    });
  }

  function newChannel() {
    const game = GAMES[publisherConfig.channels.length % GAMES.length];
    return {
      id: `canal-${Date.now().toString(36).slice(-6)}`,
      enabled: false,
      generateTime: '00:30', publishTime: '18:00',
      game: { id: game.id, difficulty: game.difficulty, duration: game.duration, theme: 'neon', soundPack: 'auto', musicMode: game.musicMode, musicVolume: 0.55, title: game.title, ...(game.id === 'soft-body-slide' ? { obstacle: 'auto' } : {}), ...(game.id === 'story-comments' ? { series: `serie-${Date.now().toString(36).slice(-6)}` } : {}) },
      tiktok: { enabled: false, username: null, musicId: null, visibility: 'private', confirmPublic: false },
      youtube: { enabled: false, account: 'default', privacy: 'private', confirmPublic: false },
    };
  }

  async function loadConfig() {
    if (!session) return;
    elements.configState.textContent = 'Chargement…';
    const [configPayload, accountPayload] = await Promise.all([control('/api/config'), control('/api/accounts')]);
    publisherConfig = structuredClone(configPayload.config);
    accountCatalog = accountPayload.accounts || { tiktok: [], youtube: [] };
    elements.configState.textContent = `${publisherConfig.channels.filter((item) => item.enabled).length} canal(aux) actif(s)`;
    elements.sessionsState.textContent = accountPayload.sessionsSynced ? `Configuration et sessions TikTok synchronisées · ${accountCatalog.syncedAt ? formatDate(accountCatalog.syncedAt) : 'prêtes'}` : 'Configuration à synchroniser depuis le Studio';
    elements.sessionsState.classList.toggle('ready', Boolean(accountPayload.sessionsSynced));
    renderChannels();
  }

  async function saveConfig() {
    if (!publisherConfig) return;
    elements.saveConfig.disabled = true;
    try {
      publisherConfig.dryRun = elements.globalMode.value === 'test';
      const payload = await control('/api/config', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(publisherConfig),
      });
      publisherConfig = structuredClone(payload.config);
      renderChannels();
      notify('Planning sauvegardé. Cloudflare et le secours GitHub utiliseront ces horaires.');
      elements.configState.textContent = `${publisherConfig.channels.filter((item) => item.enabled).length} canal(aux) actif(s)`;
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      elements.saveConfig.disabled = false;
    }
  }

  function connectGithub() {
    elements.connect.disabled = true;
    elements.connect.textContent = 'Redirection…';
    window.location.assign(`${CONTROL_API}/auth/start`);
  }

  async function verifySession() {
    if (!session) {
      lockCommands();
      return;
    }
    elements.authState.textContent = 'Connexion GitHub en cours de vérification…';
    try {
      const payload = await control('/api/session');
      const watchdog = payload.scheduler?.enabled ? ' · planificateur Cloudflare actif' : '';
      elements.authState.textContent = `Connecté en tant que ${payload.login} · GitHub App privée${watchdog}`;
      elements.authState.style.color = '#58e6a9';
      lockCommands();
      if (window.location.hash) window.history.replaceState({}, document.title, window.location.pathname);
      await Promise.all([refreshAll(), loadConfig(), audioLibrary.load()]);
    } catch (error) {
      session = '';
      forgetSession();
      lockCommands();
      elements.authState.textContent = 'Connexion expirée · reconnecte-toi avec GitHub';
      elements.authState.style.color = '#ff7088';
      notify(error instanceof Error ? error.message : String(error), true);
    }
  }

  async function disconnectGithub() {
    if (session) await control('/api/logout', { method: 'POST' }).catch(() => null);
    session = '';
    publisherConfig = null;
    accountCatalog = { tiktok: [], youtube: [] };
    audioLibrary.clear();
    forgetSession();
    elements.authState.textContent = 'Lecture publique · connexion GitHub requise pour commander';
    elements.authState.style.color = '';
    lockCommands();
    elements.connect.disabled = false;
    elements.connect.textContent = 'Se connecter avec GitHub';
    elements.configState.textContent = 'Connexion requise';
    elements.sessionsState.textContent = 'Synchronisation non vérifiée';
    elements.sessionsState.classList.remove('ready');
    renderChannels();
    notify('Session ClipMaker fermée et autorisation GitHub révoquée.');
  }

  function formatDate(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Paris',
    }).format(new Date(value));
  }

  function formatDay(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium', timeZone: 'Europe/Paris',
    }).format(new Date(value));
  }

  function runLabel(run) {
    if (run.status !== 'completed') return ['En cours', 'running'];
    if (run.conclusion === 'success') return ['Réussi', 'success'];
    if (run.conclusion === 'cancelled') return ['Annulé', 'failure'];
    return ['Échec', 'failure'];
  }

  function runActivity(runs) {
    const ordered = [...runs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    const run = ordered.find((item) => item.status !== 'completed') || ordered[0];
    if (!run) return null;
    const title = String(run.display_title || '').toLowerCase();
    let operation = 'Traitement quotidien';
    if (String(run.path || '').includes('soft-body-artifact.yml') || String(run.name || '').includes('3D')) {
      operation = 'Rendu 3D';
    } else if (title.includes('doctor')) operation = 'Vérification des comptes';
    else if (title.includes('generate')) operation = 'Génération';
    else if (title.includes('publish')) operation = 'Publication';
    return { run, operation, label: runLabel(run)[0] };
  }

  function renderRuns(runs) {
    if (!runs.length) {
      elements.runs.innerHTML = '<div class="run-row"><span class="run-state"></span><span class="run-name"><strong>Aucune exécution</strong><small>Le premier cron apparaîtra ici.</small></span></div>';
      return;
    }
    elements.runs.replaceChildren(...runs.slice(0, 6).map((run) => {
      const [result, state] = runLabel(run);
      const row = document.createElement('a');
      row.className = 'run-row';
      row.href = run.html_url;
      row.target = '_blank';
      row.rel = 'noreferrer';
      const dot = document.createElement('span');
      dot.className = `run-state ${state}`;
      const name = document.createElement('span');
      name.className = 'run-name';
      const strong = document.createElement('strong');
      strong.textContent = run.name;
      const small = document.createElement('small');
      small.textContent = `${run.event === 'schedule' ? 'Automatique' : 'Manuel'} · ${formatDate(run.created_at)}`;
      name.append(strong, small);
      const status = document.createElement('span');
      status.className = 'run-result';
      status.textContent = result;
      const arrow = document.createElement('span');
      arrow.className = 'run-link';
      arrow.textContent = '↗';
      row.append(dot, name, status, arrow);
      return row;
    }));
  }

  async function loadRuns() {
    const [daily, soft] = await Promise.all([
      github('/actions/workflows/daily-publisher.yml/runs?per_page=5&branch=main'),
      github('/actions/workflows/soft-body-artifact.yml/runs?per_page=3&branch=main'),
    ]);
    const runs = [...(daily.workflow_runs || []), ...(soft.workflow_runs || [])]
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    renderRuns(runs);
    const activity = runActivity(runs);
    elements.latestStatus.textContent = activity?.label || 'Aucune exécution';
    elements.latestTime.textContent = activity
      ? `${activity.operation} · ${formatDate(activity.run.updated_at || activity.run.created_at)}` : '—';
  }

  function extract(body, expression, fallback) {
    const match = body.match(expression);
    return match?.[1]?.trim() || fallback;
  }

  async function loadNotification() {
    const comments = await github('/issues/36/comments?per_page=100');
    const newestFirst = [...comments].reverse();
    const configured = newestFirst
      .map((comment) => comment.body.match(/Configuration\s+`([^`]+)`:\s*`([^`]+)`/i))
      .find(Boolean);
    if (configured) {
      const game = GAMES.find((item) => item.id === configured[2]);
      elements.latestChannel.textContent = configured[1];
      elements.latestOperation.textContent = `Jeu assigné : ${game?.name || configured[2]}`;
    } else {
      const latest = comments.at(-1);
      if (latest) elements.latestChannel.textContent = extract(latest.body, /Channel:\s*`([^`]+)`/i, '—');
    }

    const publishedComment = newestFirst.find((comment) => /Latest stored job:\s*`published`/iu.test(comment.body));
    const published = publishedComment?.body.match(/Latest stored job:\s*`published`\s*·\s*`([^`]+)`\s*·\s*`([^`]+)`(?:\s*·\s*`([^`]+)`)?/i);
    if (published) {
      const game = GAMES.find((item) => item.id === published[3]);
      elements.latestPublished.textContent = published[2];
      elements.latestPublishedDetail.textContent = `${game?.name || published[3] || 'Jeu historique'} · ${formatDay(`${published[1]}T12:00:00Z`)}`;
      const destinations = publishedComment?.body.match(/Destinations:\s*([^\r\n]+)/iu)?.[1] || '';
      const privateCount = destinations.match(/\(private,/giu)?.length || 0;
      const publicCount = destinations.match(/\(public,/giu)?.length || 0;
      const visibility = publicCount && privateCount
        ? 'Visibilité mixte · vérifie chaque plateforme'
        : publicCount
          ? 'Visible publiquement'
          : privateCount
            ? 'Privée · aucune vue publique'
            : 'Visibilité inconnue';
      elements.latestPublishedVisibility.textContent = visibility;
      elements.latestPublishedVisibility.classList.toggle('warning', privateCount > 0);
    }
  }

  async function loadWatchdog() {
    const response = await fetch(`${CONTROL_API}/health`, { headers: { Accept: 'application/json' } });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.scheduler) throw new Error('Le planificateur Cloudflare ne répond pas.');
    const tick = payload.lastTick;
    if (!tick) {
      elements.watchdogStatus.textContent = 'Actif · en attente';
      elements.watchdogTime.textContent = 'Premier contrôle planifié toutes les 5 minutes';
      return;
    }
    const publish = Array.isArray(tick.results)
      ? tick.results.find((item) => item.operation === 'daily-publish')
      : null;
    const detail = publish
      ? `${publish.action === 'skip' ? 'Aucun doublon' : 'Rattrapage lancé'}${publish.runId ? ` · run ${publish.runId}` : ''}`
      : 'Planning contrôlé';
    elements.watchdogStatus.textContent = tick.status === 'ok' ? 'Actif · contrôle réussi' : 'Erreur de contrôle';
    elements.watchdogTime.textContent = `${formatDate(tick.scheduledTime || tick.completedAt)} · ${detail}`;
  }

  async function refreshAll() {
    elements.refresh.disabled = true;
    elements.refresh.textContent = 'Actualisation…';
    try {
      await Promise.all([loadRuns(), loadNotification(), loadWatchdog()]);
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      elements.refresh.disabled = false;
      elements.refresh.textContent = 'Actualiser';
    }
  }

  async function dispatch(workflow, inputs, successMessage) {
    if (!session) {
      notify('Connecte-toi d’abord avec GitHub.', true);
      return;
    }
    const result = await control('/api/dispatch', {
      method: 'POST',
      body: JSON.stringify({ workflow, inputs }),
      headers: { 'Content-Type': 'application/json' },
    });
    notify(result.message || successMessage);
    setTimeout(() => void refreshAll(), 2600);
  }

  async function command(event) {
    const button = event.currentTarget;
    const action = button.dataset.command;
    if (action === 'publish' && !window.confirm('Publier maintenant la vidéo prête sur tous les comptes actifs ?')) return;
    if (action === 'generate' && !window.confirm('Lancer la génération pour les comptes et jeux du planning sauvegardé ?')) return;
    button.disabled = true;
    try {
      await dispatch('daily-publisher.yml', {
        action,
        dry_run: action === 'doctor' ? 'true' : 'false',
      }, action === 'doctor' ? 'Diagnostic GitHub lancé.' : action === 'generate' ? 'Génération réelle lancée.' : 'Publication lancée.');
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      button.disabled = false;
    }
  }

  function resolveRenderSeed(value) {
    const text = value.trim();
    if (text) {
      const seed = Number(text);
      if (!/^\d+$/u.test(text) || !Number.isSafeInteger(seed) || seed < 1 || seed > 2147483647) {
        throw new Error('La graine doit être un entier entre 1 et 2147483647.');
      }
      return String(seed);
    }
    // Reject zero rather than biasing it onto another seed. Leave the input
    // blank: another click means another variant; explicit seeds are replayable.
    const values = new Uint32Array(1);
    do { crypto.getRandomValues(values); } while ((values[0] & 0x7fffffff) === 0);
    return String(values[0] & 0x7fffffff);
  }

  async function run3d(event) {
    event.preventDefault();
    const button = elements.form3d.querySelector('button');
    button.disabled = true;
    try {
      const seed = resolveRenderSeed(document.querySelector('#seed').value);
      await dispatch('soft-body-artifact.yml', {
        obstacle: document.querySelector('#obstacle').value,
        seed,
        samples: document.querySelector('#samples').value,
        chunk_size: document.querySelector('#chunk-size').value,
        title: 'HOW SOFT CAN IT GET?',
        music_profile: document.querySelector('#three-d-music-profile').value,
      }, `Rendu Blender 3D lancé sur GitHub · graine ${seed}.`);
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      button.disabled = false;
    }
  }

  document.querySelectorAll('[data-command]').forEach((button) => button.addEventListener('click', command));
  elements.form3d.addEventListener('submit', run3d);
  elements.addChannel.addEventListener('click', () => {
    if (!publisherConfig) return;
    if (publisherConfig.channels.length >= 8) return notify('Maximum : 8 comptes par dépôt.', true);
    publisherConfig.channels.push(newChannel());
    renderChannels();
  });
  elements.saveConfig.addEventListener('click', () => void saveConfig());
  elements.reloadConfig.addEventListener('click', () => void loadConfig().catch((error) => notify(error instanceof Error ? error.message : String(error), true)));
  elements.globalMode.addEventListener('change', () => {
    if (publisherConfig) publisherConfig.dryRun = elements.globalMode.value === 'test';
  });
  elements.connect.addEventListener('click', connectGithub);
  elements.disconnect.addEventListener('click', disconnectGithub);
  elements.refresh.addEventListener('click', refreshAll);
  document.querySelectorAll('.nav-link').forEach((link) => link.addEventListener('click', () => {
    document.querySelectorAll('.nav-link').forEach((item) => item.classList.toggle('active', item === link));
  }));

  const audioLibrary = window.createEditAudioLibrary({ control, notify, connected: () => Boolean(session), media: async path => {
    await control('/api/session');
    const response = await fetch(`${CONTROL_API}${path}`, { headers: { Authorization: `Bearer ${session}` } });
    if (!response.ok) throw new Error((await response.json()).error || 'Extrait indisponible.');
    const renewed = response.headers.get('X-ClipMaker-Session');
    if (renewed) { session = renewed; saveSession(session); }
    return response.blob();
  } });

  if (session) {
    lockCommands();
    void verifySession();
  } else {
    forgetSession();
    lockCommands();
    renderChannels();
  }
  void refreshAll();
})();
