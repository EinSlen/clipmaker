import fs from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";
import {
  publisherStateDir,
  readPublisherDocument,
} from "@/lib/server-publisher-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type StoredJob = Record<string, unknown> & {
  platforms?: Record<string, Record<string, unknown>>;
  render?: Record<string, unknown>;
};

export async function GET() {
  try {
    const { raw, config } = await readPublisherDocument();
    const stateDir = publisherStateDir(raw);
    const heartbeat = await fs.readFile(path.join(stateDir, "daemon-heartbeat.json"), "utf8")
      .then(JSON.parse)
      .catch(() => null) as { at?: string; state?: string } | null;
    const lastSeen = heartbeat?.at ? Date.parse(heartbeat.at) : 0;
    const active = Boolean(lastSeen && Date.now() - lastSeen <= (config.pollSeconds + 90) * 1000);
    const state = await fs.readFile(path.join(stateDir, "publisher-state.json"), "utf8")
      .then(JSON.parse)
      .catch(() => ({ jobs: [] })) as { jobs?: StoredJob[] };
    const jobs = (Array.isArray(state.jobs) ? state.jobs : [])
      .slice()
      .sort((a, b) => String(b.updatedAt || "").localeCompare(String(a.updatedAt || "")))
      .slice(0, 20)
      .map((job) => ({
        id: String(job.id || ""),
        date: String(job.date || ""),
        channelId: String(job.channelId || ""),
        status: String(job.status || "planned"),
        updatedAt: job.updatedAt ? String(job.updatedAt) : null,
        filename: job.render?.filename ? String(job.render.filename) : null,
        outcome: job.render?.outcome ? String(job.render.outcome) : null,
        youtube: String(job.platforms?.youtube?.status || "disabled"),
        tiktok: String(job.platforms?.tiktok?.status || "disabled"),
      }));
    return NextResponse.json({
      configured: true,
      daemon: {
        active,
        state: active ? "running" : String(heartbeat?.state || "stopped"),
        lastSeenAt: heartbeat?.at || null,
      },
      jobs,
    });
  } catch {
    return NextResponse.json({
      configured: false,
      daemon: { active: false, state: "missing", lastSeenAt: null },
      jobs: [],
    });
  }
}
