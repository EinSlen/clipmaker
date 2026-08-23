import crypto from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { NextResponse } from "next/server";
import {
  hasPublisherWriteAccess,
  publisherStateDir,
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
  githubToken?: string;
};

function compressedSecret(value: unknown): string {
  return gzipSync(Buffer.from(JSON.stringify(value)), { level: 9 }).toString("base64");
}

async function setSecret(repository: string, token: string, name: string, value: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const child = spawn("gh", ["secret", "set", name, "--repo", repository], {
      env: { ...process.env, GH_TOKEN: token },
      windowsHide: true,
      stdio: ["pipe", "ignore", "pipe"],
    });
    let error = "";
    child.stderr.on("data", (chunk) => { error += chunk.toString(); });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(error.trim() || `GitHub a refusé le secret ${name}.`));
    });
    child.stdin.end(value);
  });
}

async function stateEncryptionKey(rawConfig: Record<string, unknown>): Promise<string> {
  const directory = publisherStateDir(rawConfig);
  const file = path.join(directory, "github-state-key");
  const existing = await fs.readFile(file, "utf8").catch(() => "");
  if (existing.trim()) return existing.trim();
  const generated = crypto.randomBytes(32).toString("base64");
  await fs.mkdir(directory, { recursive: true });
  await fs.writeFile(file, `${generated}\n`, { mode: 0o600 });
  return generated;
}

async function addSessionFile(files: Record<string, string>, absolute: string, warnings: string[]): Promise<void> {
  const relative = path.relative(REPO_ROOT, absolute).replaceAll("\\", "/");
  if (relative.startsWith("../") || path.isAbsolute(relative)) throw new Error("Chemin de session hors dépôt.");
  const content = await fs.readFile(absolute).catch(() => null);
  if (!content) {
    warnings.push(`Session absente : ${relative}`);
    return;
  }
  files[relative] = content.toString("base64");
}

export async function POST(request: Request) {
  if (!hasPublisherWriteAccess(request)) {
    return NextResponse.json({ ok: false, error: "Clé administrateur requise." }, { status: 401 });
  }
  try {
    const body = await request.json() as SyncBody;
    const repository = String(body.repository || "").trim();
    const githubToken = String(body.githubToken || "").trim();
    if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
      throw new Error("Dépôt GitHub invalide. Utilise propriétaire/dépôt.");
    }
    if (githubToken.length < 20 || /\s/.test(githubToken)) {
      throw new Error("Jeton GitHub invalide.");
    }
    const uploadToken = process.env.CLIPMAKER_UPLOAD_TOKEN || "";
    if (!uploadToken) throw new Error("CLIPMAKER_UPLOAD_TOKEN manque sur le serveur ClipMaker.");

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
    for (const channel of config.channels.filter((item) => item.enabled)) {
      if (channel.tiktok.enabled && channel.tiktok.username) {
        await addSessionFile(
          sessionFiles,
          path.join(TIKTOK_COOKIES_DIR, `tiktok_session-${channel.tiktok.username}.cookie`),
          warnings,
        );
      }
      if (channel.youtube.enabled) {
        const root = channel.youtube.account === "default"
          ? YOUTUBE_BROWSER_DATA_DIR
          : path.join(YOUTUBE_BROWSER_DATA_DIR, "accounts", channel.youtube.account);
        await addSessionFile(
          sessionFiles,
          path.join(root, "yt-auth", "cookies-profile-local_invalid.json"),
          warnings,
        );
      }
    }

    const configSecret = compressedSecret(cloudConfig);
    const sessionsSecret = compressedSecret({ version: 1, files: sessionFiles });
    if (configSecret.length > 47_000 || sessionsSecret.length > 47_000) {
      throw new Error("Le bundle dépasse la limite GitHub Secrets. Réduis le nombre de comptes par dépôt.");
    }
    const encryptionKey = await stateEncryptionKey(raw);
    await setSecret(repository, githubToken, "PUBLISHER_CONFIG_GZIP_B64", configSecret);
    await setSecret(repository, githubToken, "PUBLISHER_SESSIONS_GZIP_B64", sessionsSecret);
    await setSecret(repository, githubToken, "PUBLISHER_STATE_KEY", encryptionKey);
    await setSecret(repository, githubToken, "CLIPMAKER_UPLOAD_TOKEN", uploadToken);

    return NextResponse.json({
      ok: true,
      repository,
      channels: config.channels.filter((item) => item.enabled).length,
      sessionFiles: Object.keys(sessionFiles).length,
      warnings,
      actionsUrl: `https://github.com/${repository}/actions/workflows/daily-publisher.yml`,
    });
  } catch (error) {
    return NextResponse.json({
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }, { status: 400 });
  }
}
