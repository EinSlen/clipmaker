(() => {
  'use strict';

  const OWNER = 'EinSlen';
  const REPO = 'clipmaker';
  const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
  const TOKEN_KEY = 'clipmaker-github-token';
  const elements = {
    token: document.querySelector('#github-token'),
    connect: document.querySelector('#connect-token'),
    disconnect: document.querySelector('#disconnect-token'),
    tokenState: document.querySelector('#token-state'),
    refresh: document.querySelector('#refresh-all'),
    latestStatus: document.querySelector('#latest-status'),
    latestTime: document.querySelector('#latest-time'),
    latestChannel: document.querySelector('#latest-channel'),
    latestOperation: document.querySelector('#latest-operation'),
    runs: document.querySelector('#runs-list'),
    toast: document.querySelector('#toast'),
    form3d: document.querySelector('#three-d-form'),
  };

  function readStoredToken() {
    try {
      return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || '';
    } catch {
      return sessionStorage.getItem(TOKEN_KEY) || '';
    }
  }

  function saveToken(value) {
    try {
      localStorage.setItem(TOKEN_KEY, value);
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      sessionStorage.setItem(TOKEN_KEY, value);
    }
  }

  function forgetToken() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // A browser can block persistent storage while still allowing this tab.
    }
    sessionStorage.removeItem(TOKEN_KEY);
  }

  let token = readStoredToken();
  let toastTimer;

  function headers(authenticated = false) {
    const value = {
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
    };
    if (authenticated && token) value.Authorization = `Bearer ${token}`;
    return value;
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
      headers: { ...headers(Boolean(token)), ...(options.headers || {}) },
    });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.message || `GitHub a répondu ${response.status}.`);
    return payload;
  }

  function lockCommands() {
    document.querySelectorAll('.requires-token').forEach((button) => {
      button.disabled = !token;
      button.title = token ? '' : 'Connecte un jeton GitHub pour utiliser cette commande.';
    });
    if (token) {
      elements.token.value = '';
      elements.token.placeholder = 'Jeton mémorisé sur cet appareil';
    } else {
      elements.token.placeholder = 'github_pat_…';
    }
    elements.disconnect.hidden = !token;
  }

  async function connectToken() {
    const candidate = elements.token.value.trim();
    if (candidate) token = candidate;
    if (!token) {
      notify('Saisis un jeton GitHub finement limité au dépôt.', true);
      return;
    }
    elements.connect.disabled = true;
    elements.connect.textContent = 'Vérification…';
    try {
      const user = await fetch('https://api.github.com/user', { headers: headers(true) });
      const payload = await user.json();
      if (!user.ok) throw new Error(payload.message || 'Jeton refusé par GitHub.');
      saveToken(token);
      elements.tokenState.textContent = `Connecté en tant que ${payload.login} · connexion mémorisée sur cet appareil`;
      elements.tokenState.style.color = '#58e6a9';
      lockCommands();
      notify(`Connexion GitHub réussie : ${payload.login}.`);
      await refreshAll();
    } catch (error) {
      token = '';
      forgetToken();
      lockCommands();
      elements.tokenState.textContent = 'Jeton refusé · vérifie la permission Actions: write';
      elements.tokenState.style.color = '#ff7088';
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      elements.connect.disabled = false;
      elements.connect.textContent = 'Connecter';
    }
  }

  function disconnectToken() {
    token = '';
    forgetToken();
    elements.token.value = '';
    elements.tokenState.textContent = 'Lecture publique · commandes verrouillées';
    elements.tokenState.style.color = '';
    lockCommands();
    notify('Jeton GitHub retiré de cet appareil.');
  }

  function formatDate(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium', timeStyle: 'short', timeZone: 'Europe/Paris',
    }).format(new Date(value));
  }

  function runLabel(run) {
    if (run.status !== 'completed') return ['En cours', 'running'];
    if (run.conclusion === 'success') return ['Réussi', 'success'];
    if (run.conclusion === 'cancelled') return ['Annulé', 'failure'];
    return ['Échec', 'failure'];
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
      github('/actions/workflows/daily-publisher.yml/runs?per_page=5'),
      github('/actions/workflows/soft-body-artifact.yml/runs?per_page=3'),
    ]);
    const runs = [...(daily.workflow_runs || []), ...(soft.workflow_runs || [])]
      .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    renderRuns(runs);
    const latest = daily.workflow_runs?.[0];
    if (latest) {
      const [label] = runLabel(latest);
      elements.latestStatus.textContent = label;
      elements.latestTime.textContent = formatDate(latest.updated_at || latest.created_at);
    }
  }

  function extract(body, expression, fallback) {
    const match = body.match(expression);
    return match?.[1]?.trim() || fallback;
  }

  async function loadNotification() {
    const comments = await github('/issues/36/comments?per_page=20');
    const latest = comments.at(-1);
    if (!latest) return;
    elements.latestChannel.textContent = extract(latest.body, /Channel:\s*`([^`]+)`/i, '—');
    const action = extract(latest.body, /Action\s*:\s*`([^`]+)`/i, 'cron');
    const operation = extract(latest.body, /Operation:\s*`([^`]+)`/i, '—');
    elements.latestOperation.textContent = `${action} · ${operation}`;
  }

  async function refreshAll() {
    elements.refresh.disabled = true;
    elements.refresh.textContent = 'Actualisation…';
    try {
      await Promise.all([loadRuns(), loadNotification()]);
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      elements.refresh.disabled = false;
      elements.refresh.textContent = 'Actualiser';
    }
  }

  async function dispatch(workflow, inputs, successMessage) {
    if (!token) {
      notify('Connecte d’abord un jeton GitHub avec Actions: write.', true);
      return;
    }
    await github(`/actions/workflows/${workflow}/dispatches`, {
      method: 'POST',
      body: JSON.stringify({ ref: 'main', inputs }),
      headers: { 'Content-Type': 'application/json' },
    });
    notify(successMessage);
    setTimeout(() => void refreshAll(), 2600);
  }

  async function command(event) {
    const button = event.currentTarget;
    const action = button.dataset.command;
    if (action === 'publish' && !window.confirm('Publier maintenant la vidéo prête sur tous les comptes actifs ?')) return;
    if (action === 'generate' && !window.confirm('Lancer maintenant le rendu réel de la vidéo du jour ?')) return;
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

  async function run3d(event) {
    event.preventDefault();
    const button = elements.form3d.querySelector('button');
    button.disabled = true;
    try {
      await dispatch('soft-body-artifact.yml', {
        obstacle: document.querySelector('#obstacle').value,
        seed: document.querySelector('#seed').value.trim() || '910104',
        samples: document.querySelector('#samples').value,
        chunk_size: document.querySelector('#chunk-size').value,
        title: 'HOW SOFT CAN IT GET?',
      }, 'Rendu Blender 3D lancé sur GitHub.');
    } catch (error) {
      notify(error instanceof Error ? error.message : String(error), true);
    } finally {
      button.disabled = false;
    }
  }

  document.querySelectorAll('[data-command]').forEach((button) => button.addEventListener('click', command));
  elements.form3d.addEventListener('submit', run3d);
  elements.connect.addEventListener('click', connectToken);
  elements.disconnect.addEventListener('click', disconnectToken);
  elements.token.addEventListener('keydown', (event) => { if (event.key === 'Enter') void connectToken(); });
  elements.refresh.addEventListener('click', refreshAll);
  document.querySelectorAll('.nav-link').forEach((link) => link.addEventListener('click', () => {
    document.querySelectorAll('.nav-link').forEach((item) => item.classList.toggle('active', item === link));
  }));

  if (token) {
    elements.tokenState.textContent = 'Connexion mémorisée · vérification GitHub en cours';
    void connectToken();
  } else {
    lockCommands();
  }
  void refreshAll();
})();
