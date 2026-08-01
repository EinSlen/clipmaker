import fs from 'node:fs/promises';
import path from 'node:path';
import { PUBLIC_MUSIC_DIR } from './server-paths';

type JamendoTrack = {
  id: string;
  name: string;
  artist_name: string;
  audio?: string;
  audiodownload?: string;
  audiodownload_allowed?: boolean;
  license_ccurl?: string;
  shareurl?: string;
};

type JamendoResponse = {
  headers?: { status?: string; error_message?: string };
  results?: JamendoTrack[];
};

export type LicensedMusic = {
  path: string;
  title: string;
  artist: string;
  provider: 'jamendo';
  sourceUrl: string;
  licenseUrl: string;
  credit: string;
};

function slug(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 52)
    .toLowerCase() || 'track';
}

function isCommercialCcBy(track: JamendoTrack): boolean {
  const license = String(track.license_ccurl || '').toLowerCase();
  return Boolean(
    track.audiodownload_allowed &&
    track.audiodownload &&
    /\/licenses\/by\//.test(license) &&
    !license.includes('-nc') &&
    !license.includes('-nd') &&
    !license.includes('-sa')
  );
}

async function fetchWithTimeout(url: string, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      signal: controller.signal,
      headers: { 'User-Agent': 'ClipMaker/1.0 licensed-music-discovery' }
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function downloadTrack(url: string, destination: string): Promise<void> {
  const response = await fetchWithTimeout(url, 45_000);
  if (!response.ok) throw new Error(`Music download failed with HTTP ${response.status}.`);
  const declaredSize = Number(response.headers.get('content-length') || 0);
  if (declaredSize > 32 * 1024 * 1024) throw new Error('The discovered music file is larger than 32 MB.');
  const buffer = Buffer.from(await response.arrayBuffer());
  if (!buffer.length || buffer.length > 32 * 1024 * 1024) throw new Error('The discovered music file has an invalid size.');
  await fs.writeFile(destination, buffer);
}

export async function discoverLicensedMusic(seed: number): Promise<LicensedMusic | null> {
  const clientId = process.env.JAMENDO_CLIENT_ID?.trim();
  if (!clientId) return null;

  const params = new URLSearchParams({
    client_id: clientId,
    format: 'json',
    limit: '40',
    offset: String(seed % 240),
    order: 'popularity_week',
    fuzzytags: 'upbeat electronic arcade energetic',
    speed: 'high veryhigh',
    vocalinstrumental: 'instrumental',
    include: 'licenses musicinfo',
    audioformat: 'mp32',
    audiodlformat: 'mp32',
    ccnc: 'false',
    ccnd: 'false',
    ccsa: 'false'
  });
  const response = await fetchWithTimeout(`https://api.jamendo.com/v3.0/tracks/?${params}`, 20_000);
  if (!response.ok) throw new Error(`Jamendo discovery failed with HTTP ${response.status}.`);
  const payload = await response.json() as JamendoResponse;
  if (payload.headers?.status && payload.headers.status !== 'success') {
    throw new Error(payload.headers.error_message || 'Jamendo discovery failed.');
  }

  const eligible = (payload.results || []).filter(isCommercialCcBy);
  if (!eligible.length) return null;
  const track = eligible[seed % eligible.length];
  const directory = path.join(PUBLIC_MUSIC_DIR, 'licensed');
  await fs.mkdir(directory, { recursive: true });
  const destination = path.join(directory, `${track.id}-${slug(track.artist_name)}-${slug(track.name)}.mp3`);
  try {
    await fs.access(destination);
  } catch {
    await downloadTrack(String(track.audiodownload), destination);
  }

  const licenseUrl = String(track.license_ccurl);
  const sourceUrl = String(track.shareurl || 'https://www.jamendo.com/');
  return {
    path: destination,
    title: track.name,
    artist: track.artist_name,
    provider: 'jamendo',
    sourceUrl,
    licenseUrl,
    credit: `Music: ${track.name} — ${track.artist_name} · ${sourceUrl} · CC BY ${licenseUrl}`
  };
}
