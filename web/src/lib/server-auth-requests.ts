import fs from "node:fs/promises";
import path from "node:path";
import { REPO_ROOT } from "@/lib/server-paths";

export type AuthPlatform = "tiktok" | "youtube";

function requestFile(platform: AuthPlatform): string {
  return path.join(REPO_ROOT, "web", "data", "auth", `${platform}-request.txt`);
}

export async function requestInteractiveAuth(platform: AuthPlatform, account: string): Promise<void> {
  const file = requestFile(platform);
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  const value = `${Date.now()}-${Math.random().toString(36).slice(2, 9)}|${account}\n`;
  await fs.writeFile(temporary, value, { mode: 0o600 });
  await fs.rename(temporary, file).catch(async () => {
    await fs.copyFile(temporary, file);
    await fs.rm(temporary, { force: true });
  });
}

export function interactiveAuthUrl(request: Request, platform: AuthPlatform): string {
  const requestUrl = new URL(request.url);
  const port = platform === "youtube" ? 6080 : 6081;
  return `http://${requestUrl.hostname}:${port}/vnc.html?autoconnect=true&resize=scale`;
}
