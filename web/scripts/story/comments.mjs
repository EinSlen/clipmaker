import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { TIKTOK_UPLOADER_DIR } from './paths.mjs';

const YOUTUBE_API = 'https://www.googleapis.com/youtube/v3/commentThreads';
const SCRAPER = path.join(path.dirname(fileURLToPath(import.meta.url)), 'tiktok-comments.cjs');

function normalize(platform, author, text, likes, publishedAt) {
  const body = String(text || '').replace(/\s+/g, ' ').trim();
  return {
    platform,
    author: String(author || 'someone').replace(/\s+/g, ' ').trim().slice(0, 40),
    text: body.slice(0, 400),
    likes: Number.isFinite(Number(likes)) ? Number(likes) : 0,
    publishedAt: publishedAt || null,
  };
}

export async function fetchYoutubeComments(videoId, { max = 60 } = {}) {
  const key = process.env.YOUTUBE_API_KEY;
  if (!key) return { ok: false, reason: 'no-youtube-api-key', comments: [] };
  if (!/^[\w-]{6,20}$/.test(String(videoId || ''))) return { ok: false, reason: 'no-video-id', comments: [] };
  const url = new URL(YOUTUBE_API);
  url.searchParams.set('part', 'snippet');
  url.searchParams.set('videoId', videoId);
  url.searchParams.set('order', 'relevance');
  url.searchParams.set('maxResults', String(Math.min(100, max)));
  url.searchParams.set('textFormat', 'plainText');
  url.searchParams.set('key', key);
  const response = await fetch(url).catch((error) => ({ ok: false, statusText: error.message }));
  if (!response.ok) {
    const detail = typeof response.text === 'function' ? await response.text().catch(() => '') : '';
    // Comments disabled or the video is still private: not a pipeline failure.
    return { ok: false, reason: `youtube-http-${response.status || 0}`, detail: detail.slice(0, 200), comments: [] };
  }
  const payload = await response.json();
  const comments = (payload.items || []).map((item) => {
    const snippet = item?.snippet?.topLevelComment?.snippet || {};
    return normalize('youtube', snippet.authorDisplayName, snippet.textOriginal, snippet.likeCount, snippet.publishedAt);
  });
  return { ok: true, comments: comments.filter((comment) => comment.text) };
}

export function fetchTiktokComments(username, videoId, { max = 60, timeoutMs = 120_000 } = {}) {
  const scraperArgs = [SCRAPER, '--user', username, '--video', String(videoId), '--max', String(max)];
  // The browser has to be a real window; on a Linux runner that means Xvfb.
  const virtualDisplay = process.platform === 'linux' && !process.env.DISPLAY;
  const command = virtualDisplay ? 'xvfb-run' : process.execPath;
  const commandArgs = virtualDisplay
    ? ['-a', '--server-args=-screen 0 1440x1000x24', process.execPath, ...scraperArgs]
    : scraperArgs;
  return new Promise((resolve) => {
    // The scraper reads CookiesDir relative to its working directory, exactly
    // like the upload agent does.
    const child = spawn(command, commandArgs, {
      cwd: TIKTOK_UPLOADER_DIR,
      windowsHide: true,
      env: process.env,
    });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => child.kill(), timeoutMs);
    child.stdout.on('data', (chunk) => { stdout += chunk.toString(); });
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
    child.on('error', (error) => {
      clearTimeout(timer);
      resolve({ ok: false, reason: `tiktok-spawn: ${error.message}`, comments: [] });
    });
    child.on('close', () => {
      clearTimeout(timer);
      const line = stdout.split(/\r?\n/).reverse().find((entry) => entry.startsWith('CLIPMAKER_COMMENTS:'));
      if (!line) {
        resolve({ ok: false, reason: 'tiktok-no-output', detail: stderr.slice(-200), comments: [] });
        return;
      }
      try {
        const parsed = JSON.parse(line.slice('CLIPMAKER_COMMENTS:'.length));
        resolve({
          ok: parsed.ok !== false,
          ...(parsed.ok === false ? { reason: String(parsed.error || 'tiktok-failed') } : {}),
          ...(parsed.captcha ? { captcha: true } : {}),
          comments: (parsed.comments || []).map((comment) => normalize('tiktok', comment.author, comment.text, comment.likes, comment.publishedAt)),
        });
      } catch {
        resolve({ ok: false, reason: 'tiktok-bad-output', comments: [] });
      }
    });
  });
}

export async function harvestComments(previous) {
  if (!previous) return { comments: [], sources: [{ platform: 'none', ok: false, reason: 'no-previous-episode' }] };
  const sources = [];
  const collected = [];
  const youtubeId = previous.publishedIds?.youtube;
  if (youtubeId) {
    const result = await fetchYoutubeComments(youtubeId);
    sources.push({ platform: 'youtube', ok: result.ok, reason: result.reason, count: result.comments.length });
    collected.push(...result.comments);
  }
  const tiktokId = previous.publishedIds?.tiktok;
  const tiktokUser = previous.publishedIds?.tiktokUsername;
  if (tiktokId && tiktokUser) {
    const result = await fetchTiktokComments(tiktokUser, tiktokId);
    sources.push({ platform: 'tiktok', ok: result.ok, reason: result.reason, count: result.comments.length });
    collected.push(...result.comments);
  }
  const seen = new Set();
  const comments = collected
    .filter((comment) => {
      const fingerprint = `${comment.platform}|${comment.author}|${comment.text.toLowerCase()}`;
      if (seen.has(fingerprint)) return false;
      seen.add(fingerprint);
      return comment.text.length >= 3;
    })
    .sort((a, b) => b.likes - a.likes)
    .slice(0, 80);
  return { comments, sources };
}
