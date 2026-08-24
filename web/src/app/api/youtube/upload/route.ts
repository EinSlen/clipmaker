import crypto from 'node:crypto';
import path from 'node:path';
import fs from 'node:fs/promises';
import { NextResponse } from 'next/server';
import { RENDERS_DIR } from '@/lib/server-paths';
import { probeVideo } from '@/lib/ffmpeg';
import { getYouTubeDoctorStatus, uploadYouTubeShort } from '@/lib/youtube-agent';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 600;

type Body = {
  filename?: string;
  title?: string;
  description?: string;
  tags?: string[];
  privacy?: 'private' | 'unlisted' | 'public';
  confirmPublic?: boolean;
  account?: string;
};

function hasValidAdminToken(req: Request): boolean {
  const expected = process.env.CLIPMAKER_UPLOAD_TOKEN || '';
  const supplied = req.headers.get('x-clipmaker-upload-token') || '';
  if (!expected || !supplied) return false;
  const a = Buffer.from(expected);
  const b = Buffer.from(supplied);
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export async function POST(req: Request) {
  try {
    const body = (await req.json()) as Body;
    const filename = path.basename(String(body.filename || ''));
    if (!filename || !/\.(mp4|mov|m4v|webm)$/i.test(filename)) {
      return NextResponse.json({ ok: false, error: 'Nom de rendu vidéo invalide' }, { status: 400 });
    }

    const videoAbs = path.join(RENDERS_DIR, filename);
    const stat = await fs.stat(videoAbs).catch(() => null);
    if (!stat?.isFile() || stat.size === 0) {
      return NextResponse.json({ ok: false, error: 'Rendu introuvable ou vide' }, { status: 400 });
    }

    const title = String(body.title || '').trim();
    if (!title || title.length > 100 || /[<>]/.test(title)) {
      return NextResponse.json({ ok: false, error: 'Titre YouTube invalide (1 à 100 caractères, sans < ou >)' }, { status: 400 });
    }

    const description = String(body.description || '').trim().slice(0, 5000);
    const tags = Array.isArray(body.tags)
      ? body.tags.map((tag) => String(tag).trim().replace(/^#/, '')).filter(Boolean).slice(0, 15)
      : [];
    const privacy = body.privacy || 'private';
    if (!['private', 'unlisted', 'public'].includes(privacy)) {
      return NextResponse.json({ ok: false, error: 'Confidentialité YouTube invalide' }, { status: 400 });
    }

    const media = await probeVideo(videoAbs);
    if (!media || !Number.isFinite(media.duration) || media.duration <= 0 || media.duration > 180) {
      return NextResponse.json({ ok: false, error: 'Un Short doit durer entre 1 et 180 secondes' }, { status: 400 });
    }
    if (media.width <= 0 || media.height <= 0 || media.width > media.height) {
      return NextResponse.json({ ok: false, error: 'Un Short doit être carré ou vertical' }, { status: 400 });
    }

    const account = String(body.account || 'default').trim().toLowerCase();
    const status = await getYouTubeDoctorStatus(account);
    if (!status.dry_run) {
      if (!status.ready_for_live_upload) {
        return NextResponse.json({
          ok: false,
          error: status.next_steps.join(' ') || 'Le compte YouTube n’est pas prêt pour la publication.',
        }, { status: 503 });
      }
      if (!hasValidAdminToken(req)) {
        return NextResponse.json({ ok: false, error: "Jeton d'administration requis pour un upload réel" }, { status: 401 });
      }
    }

    if (privacy === 'public') {
      if (process.env.YOUTUBE_ALLOW_PUBLIC_UPLOAD !== 'true') {
        return NextResponse.json({ ok: false, error: 'Les uploads publics sont désactivés' }, { status: 403 });
      }
      if (!body.confirmPublic) {
        return NextResponse.json({ ok: false, error: 'Confirmation explicite requise pour publier en public' }, { status: 400 });
      }
    }

    const result = await uploadYouTubeShort({
      videoPath: videoAbs,
      title,
      caption: description || title,
      tags,
      durationSeconds: media.duration,
      aspectRatio: media.width === media.height ? '1:1' : '9:16',
      privacy,
      account,
    });

    return NextResponse.json({
      ok: true,
      dryRun: result.dry_run,
      account,
      media,
      upload: result.result
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: (error instanceof Error ? error.message : String(error)).slice(0, 2000) },
      { status: 500 }
    );
  }
}
