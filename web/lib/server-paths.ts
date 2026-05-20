import path from 'node:path';

// In Docker we mount the parent repo at /repo and pass REPO_ROOT=/repo.
export const REPO_ROOT = process.env.REPO_ROOT
  ? path.resolve(process.env.REPO_ROOT)
  : path.resolve(process.cwd(), '..');
export const UPLOADS_DIR = path.resolve(process.cwd(), 'uploads');
export const RENDERS_DIR = path.resolve(process.cwd(), 'renders');
export const PUBLIC_MUSIC_DIR = path.resolve(process.cwd(), 'public', 'music');
export const TIKTOK_UPLOADER_DIR = path.join(REPO_ROOT, 'vendor', 'TiktokAutoUploader');
export const TIKTOK_COOKIES_DIR = path.join(TIKTOK_UPLOADER_DIR, 'CookiesDir');
