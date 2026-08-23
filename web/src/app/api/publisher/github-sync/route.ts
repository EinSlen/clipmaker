import fs from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { NextResponse } from "next/server";
import {
  hasPublisherWriteAccess,
  readPublisherDocument,
} from "@/lib/server-publisher-config";
import {
  REPO_ROOT,
  TIKTOK_COOKIES_DIR,
  YOUTUBE_BROWSER_DATA_DIR,
} from "@/lib/server-paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SyncBody = {
  repository?: string;
};

function compressedSecret(value: unknown): string {
  return gzipSync(Buffer.from(JSON.stringify(value)), { level: 9 }).toString("base64");
}

async function addSessionFile(files: Record<string, string>, absolute: string, warnings: string[]): Promise<boolean> {
  const relative = path.relative(REPO_ROOT, absolute).replaceAll("\\", "/");
  if (relative.startsWith("../") || path.isAbsolute(relative)) throw new Error("Chemin de session hors dépôt.");
  const content = await fs.readFile(absolute).catch(() => null);
  if (!content) {
    warnings.push(`Session absente : ${relative}`);
    return false;
  }
  files[relative] = content.toString("base64");
  return true;
}

export async function POST(request: Request) {
  if (!hasPublisherWriteAccess(request)) {
    return NextResponse.json({ ok: false, error: "Clé administrateur requise." }, { status: 401 });
  }
  try {
    const body = await request.json() as SyncBody;
    const repository = String(body.repository || "EinSlen/clipmaker").trim();
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
      throw new Error("Dépôt GitHub invalide. Utilise propriétaire/dépôt.");
    }
    const uploadToken = process.env.CLIPMAKER_UPLOAD_TOKEN || "";
    if (!uploadToken) throw new Error("CLIPMAKER_UPLOAD_TOKEN manque sur le serveur ClipMaker.");
    const cloudControlUrl = String(
      process.env.CLIPMAKER_CLOUD_CONTROL_URL || "https://clipmaker-cloud-control.einslen.workers.dev",
    ).replace(/\/$/, "");

    const { raw, config } = await readPublisherDocument();
    const cloudConfig = {
      ...raw,
      ...config,
      baseUrl: "http://127.0.0.1:3000",
      requestTimeoutMinutes: raw.requestTimeoutMinutes ?? 1440,
      seedNamespace: raw.seedNamespace ?? "clipmaker-daily-v1",
      stateDir: "../data/publisher",
    };
    const sessionFiles: Record<string, string> = {};
    const warnings: string[] = [];
    const accounts: {
      tiktok: Array<{ username: string; ready: boolean }>;
      youtube: Array<{ id: string; label: string; ready: boolean }>;
    } = { tiktok: [], youtube: [] };
    for (const channel of config.channels.filter((item) => item.enabled)) {
      if (channel.tiktok.enabled && channel.tiktok.username) {
        const ready = await addSessionFile(
          sessionFiles,
          path.join(TIKTOK_COOKIES_DIR, `tiktok_session-${channel.tiktok.username}.cookie`),
          warnings,
        );
        if (!accounts.tiktok.some((item) => item.username.toLowerCase() === channel.tiktok.username?.toLowerCase())) {
          accounts.tiktok.push({ username: channel.tiktok.username, ready });
        }
      }
      if (channel.youtube.enabled) {
        const root = channel.youtube.account === "default"
          ? YOUTUBE_BROWSER_DATA_DIR
          : path.join(YOUTUBE_BROWSER_DATA_DIR, "accounts", channel.youtube.account);
        const ready = await addSessionFile(
          sessionFiles,
          path.join(root, "yt-auth", "cookies-profile-local_invalid.json"),
          warnings,
        );
        if (!accounts.youtube.some((item) => item.id.toLowerCase() === channel.youtube.account.toLowerCase())) {
          accounts.youtube.push({ id: channel.youtube.account, label: channel.youtube.account, ready });
        }
      }
    }

    const sessionsSecret = compressedSecret({ version: 1, files: sessionFiles });
    if (sessionsSecret.length > 60_000) {
      throw new Error("Le bundle de sessions est trop volumineux. Réduis le nombre de comptes par dépôt.");
    }
    const cloudResponse = await fetch(`${cloudControlUrl}/api/workflow/bootstrap`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${uploadToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ config: cloudConfig, sessionsBundle: sessionsSecret, accounts }),
      cache: "no-store",
    });
    const cloudPayload = await cloudResponse.json().catch(() => ({})) as { error?: string };
    if (!cloudResponse.ok) throw new Error(cloudPayload.error || "Le contrôle Cloudflare a refusé la synchronisation.");

    return NextResponse.json({
      ok: true,
      repository,
      channels: config.channels.filter((item) => item.enabled).length,
      sessionFiles: Object.keys(sessionFiles).length,
      warnings,
      actionsUrl: `https://github.com/${repository}/actions/workflows/daily-publisher.yml`,
      dashboardUrl: "https://einslen.github.io/clipmaker/",
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, { status: 400 });
  }
}
