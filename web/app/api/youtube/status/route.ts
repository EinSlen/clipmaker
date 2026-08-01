import { NextResponse } from 'next/server';
import { getYouTubeDoctorStatus } from '@/lib/youtube-agent';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const status = await getYouTubeDoctorStatus();
    return NextResponse.json({
      ok: true,
      dryRun: status.dry_run,
      readyForLiveUpload: status.ready_for_live_upload,
      configured: status.configured,
      defaultPrivacy: 'private',
      publicUploadAllowed: process.env.YOUTUBE_ALLOW_PUBLIC_UPLOAD === 'true',
      liveUploadRequiresToken: true
    });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : String(error) },
      { status: 500 }
    );
  }
}
