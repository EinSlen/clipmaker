import path from 'node:path';

// Mirrors src/lib/server-paths.ts. In Docker the app runs from /app while the
// persisted state lives in the repository mounted at /repo, so the story
// memory must never be resolved from the current working directory.
export const REPO_ROOT = process.env.REPO_ROOT
  ? path.resolve(process.env.REPO_ROOT)
  : path.resolve(process.cwd(), '..');

export const WEB_DATA_DIR = path.join(REPO_ROOT, 'web', 'data');
export const STORY_DIR = path.join(WEB_DATA_DIR, 'story');
export const PUBLISHER_STATE_FILE = path.join(WEB_DATA_DIR, 'publisher', 'publisher-state.json');
export const TIKTOK_UPLOADER_DIR = path.join(REPO_ROOT, 'vendor', 'TiktokAutoUploader');
