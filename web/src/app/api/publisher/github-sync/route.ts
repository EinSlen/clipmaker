import fs from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { NextResponse } from "next/server";
import {
  hasPublisherWriteAccess,
  readPublisherDocument,
} from "@/lib/server-publisher-config";
import {
  MINIMAX_SESSION_FILE,
  REPO_ROOT,
  TIKTOK_COOKIES_DIR,
} from "@/lib/server-paths";
import { listYouTubeAccounts } from "@/lib/youtube-agent";
import { collidingChannels, readTikTokIdentities } from "@/lib/tiktok-identity";

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
      tiktok: Array<{ username: string; ready: boolean; accountId?: string }>;
      youtube: Array<{ id: string; label: string; ready: boolean }>;
    } = { tiktok: [], youtube: [] };
    const configuredYoutubeAccounts = await listYouTubeAccounts();
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
        const ready = configuredYoutubeAccounts.some((item) => (
          item.id.toLowerCase() === channel.youtube.account.toLowerCase() && item.configured
        ));
        if (!accounts.youtube.some((item) => item.id.toLowerCase() === channel.youtube.account.toLowerCase())) {
          accounts.youtube.push({ id: channel.youtube.account, label: channel.youtube.account, ready });
        }
      }
    }

    // Two channels on one TikTok account post twice a day from the same
    // profile. That went unnoticed here for weeks because the two sessions
    // carried different labels, so the check has to compare the account
    // behind them rather than the names in the configuration.
    const tiktokAssignments = config.channels
      .filter((channel) => channel.enabled && channel.tiktok.enabled && channel.tiktok.username)
      .map((channel) => ({ channelId: channel.id, username: channel.tiktok.username as string }));
    if (tiktokAssignments.length > 1) {
      const identities = await readTikTokIdentities().catch((error) => {
        warnings.push(`Identité TikTok non vérifiée : ${error instanceof Error ? error.message : "inconnue"}`);
        return { accounts: [], shared: [] };
      });
      for (const account of identities.accounts || []) {
        const entry = accounts.tiktok.find((item) => item.username === account.username);
        if (entry && account.accountId) entry.accountId = account.accountId;
      }
      const collisions = collidingChannels(identities, tiktokAssignments);
      if (collisions.length) {
        const [collision] = collisions;
        throw new Error(
          `Les canaux ${collision.channels.join(" et ")} publient sur le même compte TikTok `
          + `(sessions ${collision.usernames.join(", ")}). Donne un compte par canal avant de synchroniser.`,
        );
      }
    }

    // The comment driven channel generates its clips through the Minimax
    // browser agent, which needs its own session on the runner.
    const needsMinimax = config.channels.some((item) => item.enabled && item.game.id === "story-comments");
    if (needsMinimax) await addSessionFile(sessionFiles, MINIMAX_SESSION_FILE, warnings);

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
