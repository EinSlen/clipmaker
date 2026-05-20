'use client';

import type { LibraryVideo } from './types';

const DB_NAME = 'clipmaker';
const DB_VERSION = 1;
const STORE = 'videos';

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'id' });
        store.createIndex('createdAt', 'createdAt');
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function putVideo(record: LibraryVideo & { blob: Blob }): Promise<void> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getVideo(id: string): Promise<(LibraryVideo & { blob: Blob }) | undefined> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).get(id);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function listVideos(): Promise<LibraryVideo[]> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => {
      const items = (req.result as (LibraryVideo & { blob?: Blob })[]) ?? [];
      items.sort((a, b) => b.createdAt - a.createdAt);
      resolve(items.map(({ blob: _omit, ...rest }) => rest));
    };
    req.onerror = () => reject(req.error);
  });
}

export async function deleteVideo(id: string): Promise<void> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function probeVideo(blob: Blob): Promise<{ duration: number; width: number; height: number; thumb?: string }> {
  return new Promise((resolve, reject) => {
    const video = document.createElement('video');
    video.preload = 'metadata';
    video.muted = true;
    video.src = URL.createObjectURL(blob);
    video.onloadedmetadata = () => {
      const meta = { duration: video.duration, width: video.videoWidth, height: video.videoHeight };
      // Try to grab a thumbnail at 1s
      video.currentTime = Math.min(1, Math.max(0, video.duration / 4));
      video.onseeked = () => {
        try {
          const canvas = document.createElement('canvas');
          canvas.width = 320;
          canvas.height = Math.round((video.videoHeight / video.videoWidth) * 320) || 568;
          const ctx = canvas.getContext('2d');
          if (ctx) {
            ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
            resolve({ ...meta, thumb: canvas.toDataURL('image/jpeg', 0.6) });
          } else {
            resolve(meta);
          }
        } catch {
          resolve(meta);
        } finally {
          URL.revokeObjectURL(video.src);
        }
      };
    };
    video.onerror = () => reject(new Error('Impossible de lire la vidéo'));
  });
}
