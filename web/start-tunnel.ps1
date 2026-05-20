# Lance Next.js + Cloudflare Tunnel et affiche l'URL publique à coller dans le tel.
# Utilisation : depuis le dossier web/  →  pwsh ./start-tunnel.ps1
$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path "$PSScriptRoot\.."
$cloudflared = Join-Path $repoRoot ".bin\cloudflared.exe"

if (-not (Test-Path $cloudflared)) {
  Write-Host "→ Téléchargement de cloudflared.exe…" -ForegroundColor Cyan
  New-Item -ItemType Directory -Force -Path (Split-Path $cloudflared) | Out-Null
  Invoke-WebRequest -UseBasicParsing `
    -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' `
    -OutFile $cloudflared
}

# Build s'il manque
if (-not (Test-Path "$PSScriptRoot\.next")) {
  Write-Host "→ Build Next.js…" -ForegroundColor Cyan
  Push-Location $PSScriptRoot
  npm run build
  Pop-Location
}

# Démarre Next.js (background)
Write-Host "→ Démarrage de Next.js sur :3000…" -ForegroundColor Cyan
$next = Start-Process -PassThru -WindowStyle Hidden -WorkingDirectory $PSScriptRoot `
  -FilePath "npx.cmd" -ArgumentList "next","start","-p","3000"

Start-Sleep -Seconds 5

# Démarre cloudflared (foreground, affiche l'URL)
Write-Host "→ Ouverture du tunnel public…" -ForegroundColor Cyan
Write-Host "   (Ctrl+C pour stopper. Next.js sera tué aussi.)" -ForegroundColor DarkGray
try {
  & $cloudflared tunnel --no-autoupdate --url http://localhost:3000
}
finally {
  if ($next -and -not $next.HasExited) {
    Stop-Process -Id $next.Id -Force -ErrorAction SilentlyContinue
  }
}
