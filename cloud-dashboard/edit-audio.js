/* Private spoken-audio editor. Decodes locally; only the reviewed excerpt is uploaded. */
(() => {
  window.createEditAudioLibrary = ({ control, media, notify, connected }) => {
    const form = document.querySelector('#edit-audio-form');
    const list = document.querySelector('#edit-audio-list');
    const state = document.querySelector('#edit-audio-state');
    const player = document.querySelector('#edit-audio-player');
    const input = name => form.elements.namedItem(name);
    let decoded = null;
    let preview = null;
    let previewKey = '';
    let playerUrl = '';
    let clips = [];
    let collection = null;
    let revision = 0;
    const key = () => `${input('start').value}:${input('end').value}`;
    const playBlob = blob => {
      player.pause();
      if (playerUrl) URL.revokeObjectURL(playerUrl);
      playerUrl = URL.createObjectURL(blob);
      player.src = playerUrl;
      player.hidden = false;
    };
    function clear() {
      decoded = null; invalidate(); clips = []; collection = null;
      player.pause(); player.removeAttribute('src'); player.hidden = true;
      if (playerUrl) URL.revokeObjectURL(playerUrl);
      playerUrl = '';
      list.replaceChildren(); state.textContent = 'Connexion requise';
    }
    function invalidate() { revision++; preview = null; previewKey = ''; input('speechReviewed').checked = false; }
    input('start').addEventListener('input', invalidate);
    input('end').addEventListener('input', invalidate);
    input('file').addEventListener('change', async () => {
      decoded = null; invalidate();
      const current = revision;
      const file = input('file').files[0];
      if (!file) return;
      if (file.size > 30 * 1024 * 1024) return notify('Fichier source limité à 30 Mo.', true);
      const context = new AudioContext();
      try {
        const audio = await context.decodeAudioData(await file.arrayBuffer());
        if (current !== revision) return;
        if (!Number.isFinite(audio.duration) || audio.duration < 10 || audio.duration > 600) throw new Error('Source attendue : 10 secondes à 10 minutes.');
        decoded = audio;
        input('start').value = '0';
        input('end').value = String(Math.min(29.5, decoded.duration));
        state.textContent = `Source : ${decoded.duration.toFixed(1)} s · choisis des phrases complètes`;
      } catch (error) { if (current === revision) { decoded = null; notify(error.message || 'Format audio non reconnu.', true); } }
      finally { await context.close(); }
    });
    async function excerpt() {
      if (!decoded) throw new Error('Choisis un fichier audio.');
      const start = Number(input('start').value), end = Number(input('end').value);
      const duration = end - start;
      if (!Number.isFinite(duration) || start < 0 || end > decoded.duration + .00001 || duration < 10 || duration > 29.5) throw new Error('Choisis 10 à 29,5 secondes, sans couper de phrase.');
      const frames = Math.round(duration * 48000);
      const context = new OfflineAudioContext(2, frames, 48000);
      const source = context.createBufferSource(); source.buffer = decoded; source.connect(context.destination);
      source.start(0, start, duration);
      const rendered = await context.startRendering();
      const left = rendered.getChannelData(0), right = rendered.getChannelData(1);
      const bytes = new ArrayBuffer(44 + frames * 4), view = new DataView(bytes);
      const text = (offset, value) => [...value].forEach((char, i) => view.setUint8(offset + i, char.charCodeAt(0)));
      text(0, 'RIFF'); view.setUint32(4, bytes.byteLength - 8, true); text(8, 'WAVEfmt ');
      view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 2, true);
      view.setUint32(24, 48000, true); view.setUint32(28, 192000, true); view.setUint16(32, 4, true);
      view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, frames * 4, true);
      for (let i = 0; i < frames; i++) {
        view.setInt16(44 + i * 4, Math.round(Math.max(-1, Math.min(1, left[i])) * 32767), true);
        view.setInt16(46 + i * 4, Math.round(Math.max(-1, Math.min(1, right[i])) * 32767), true);
      }
      return new Blob([bytes], { type: 'audio/wav' });
    }
    document.querySelector('#preview-edit-audio').addEventListener('click', async () => {
      const current = revision, currentKey = key();
      try {
        const audio = await excerpt();
        if (current !== revision || currentKey !== key()) return;
        playBlob(audio); await player.play();
        if (current === revision && currentKey === key()) { preview = audio; previewKey = currentKey; }
      } catch (error) { if (current === revision) notify(error.message, true); }
    });
    function render() {
      const auto = collection?.enabled === false ? 'collecte Internet en pause'
        : collection?.status === 'not-run' ? 'collecte Internet prête'
          : `collecte ${collection?.status || 'inconnue'}${collection?.completedAt ? ` · ${new Date(collection.completedAt).toLocaleString('fr-FR')}` : ''}`;
      state.textContent = `${clips.filter(clip => clip.active).length} extraits actifs · ${auto}`;
      list.replaceChildren();
      if (!clips.length) { list.textContent = 'Aucune voix importée. Le mode voix ne prendra jamais une chanson à la place.'; return; }
      for (const clip of clips) {
        const row = document.createElement('article'); row.className = 'edit-audio-row';
        const copy = document.createElement('div');
        const title = document.createElement('strong'); title.textContent = clip.title;
        const details = document.createElement('small');
        details.textContent = `${clip.mood === 'sad' ? 'Triste' : 'Revenge'} · ${clip.duration.toFixed(1)} s · ${clip.mix === 'premixed' ? 'mix original conservé' : 'voix + fond discret'} · ${clip.reviewMode === 'freesound-whisper-v1' ? 'Internet · contrôle automatique CC' : 'validé manuellement'} · ${clip.active ? 'actif' : 'désactivé'}`;
        copy.append(title, details);
        if (/^https:\/\//u.test(clip.source || '')) {
          const source = document.createElement('a'); source.href = clip.source; source.target = '_blank'; source.rel = 'noreferrer';
          source.textContent = clip.reviewMode === 'freesound-whisper-v1' ? 'Source et licence ↗' : 'Source ↗'; copy.append(source);
        }
        const listen = document.createElement('button'); listen.type = 'button'; listen.className = 'button button-secondary'; listen.textContent = 'Écouter';
        listen.addEventListener('click', async () => {
          listen.disabled = true;
          try { playBlob(await media(`/api/edit-audio/${clip.id}`)); await player.play(); }
          catch (error) { notify(error.message, true); }
          finally { listen.disabled = false; }
        });
        const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'button button-secondary'; toggle.textContent = clip.active ? 'Désactiver' : 'Réactiver';
        toggle.addEventListener('click', async () => {
          if (clip.active && !window.confirm('Désactiver cet extrait ? Un rendu qui l’avait déjà choisi sera bloqué plutôt que remplacé.')) return;
          toggle.disabled = true;
          try {
            const result = await control(`/api/edit-audio/${clip.id}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: !clip.active }) });
            Object.assign(clip, result.clip); render();
          } catch (error) { notify(error.message, true); toggle.disabled = false; }
        });
        row.append(copy, listen, toggle); list.append(row);
      }
    }
    async function load() {
      if (!connected()) { clear(); return; }
      try { [clips, collection] = await Promise.all([control('/api/edit-audio').then(value => value.clips), control('/api/edit-audio/collection')]); render(); }
      catch (error) { state.textContent = 'Bibliothèque indisponible'; notify(error.message, true); }
    }
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]'); button.disabled = true;
      try {
        if (!connected()) throw new Error('Connecte-toi avec GitHub.');
        if (!preview || previewKey !== key()) throw new Error('Écoute d’abord l’extrait exact avec le bouton d’aperçu.');
        const metadata = Object.fromEntries(['title', 'mood', 'mix', 'rights', 'rightsEvidence', 'credit', 'source'].map(name => [name, input(name).value.trim()]));
        metadata.speechReviewed = input('speechReviewed').checked;
        metadata.rightsConfirmed = input('rightsConfirmed').checked;
        const body = new FormData(); body.append('metadata', JSON.stringify(metadata)); body.append('audio', preview, 'spoken.wav');
        const result = await control('/api/edit-audio', { method: 'POST', body });
        clips.push(result.clip); render(); form.reset(); decoded = null; invalidate();
        notify('Extrait ajouté. Il est conservé dans le cloud, même ordinateur éteint.');
      } catch (error) { notify(error.message, true); }
      finally { button.disabled = !connected(); }
    });
    document.querySelector('#reload-edit-audio').addEventListener('click', () => void load());
    document.querySelector('#toggle-edit-audio-collection').addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      try {
        collection = await control('/api/edit-audio/collection', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: collection?.enabled === false }) });
        render(); notify(collection.enabled ? 'Collecte Internet quotidienne activée.' : 'Collecte Internet mise en pause.');
      } catch (error) { notify(error.message, true); }
      finally { event.currentTarget.disabled = false; }
    });
    document.querySelector('#run-edit-audio-collection').addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      try {
        await control('/api/dispatch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ workflow: 'edit-audio-discovery.yml', inputs: {} }) });
        notify('Recherche Internet lancée sur GitHub. Le résultat apparaîtra ici après analyse.');
      } catch (error) { notify(error.message, true); }
      finally { event.currentTarget.disabled = false; }
    });
    window.addEventListener('pagehide', () => { if (playerUrl) URL.revokeObjectURL(playerUrl); });
    return { load, clear };
  };
})();
