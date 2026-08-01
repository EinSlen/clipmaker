import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(scriptDir, '..');
const repoRoot = path.resolve(webDir, '..');
const configDir = process.env.YOUTUBE_AGENT_CONFIG_DIR
  ? path.resolve(process.env.YOUTUBE_AGENT_CONFIG_DIR)
  : path.join(repoRoot, '.youtube-agent');
const packageDir = path.join(webDir, 'node_modules', 'youtube-shorts-agent');

fs.mkdirSync(configDir, { recursive: true });

const [command = 'doctor', ...args] = process.argv.slice(2);
const isAuth = command === 'auth';
const entrypoint = path.join(
  packageDir,
  'src',
  ...(isAuth ? ['tools', 'youtube-oauth.js'] : ['cli.js'])
);

if (!fs.existsSync(entrypoint)) {
  console.error('youtube-shorts-agent is missing. Run npm install first.');
  process.exit(1);
}

const childArgs = isAuth
  ? [entrypoint, 'start-auth', '--redirect', process.env.YOUTUBE_REDIRECT_URI || 'http://localhost:8788/callback', ...args]
  : [entrypoint, command, ...args];

const child = spawn(process.execPath, childArgs, {
  cwd: configDir,
  env: {
    ...process.env,
    YOUTUBE_AGENT_DATA_DIR: path.join(configDir, '.agent-data')
  },
  stdio: 'inherit',
  windowsHide: true
});

child.on('error', (error) => {
  console.error(String(error));
  process.exitCode = 1;
});
child.on('exit', (code) => {
  process.exitCode = code ?? 1;
});
