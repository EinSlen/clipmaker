# Deploy clipMaker to HuggingFace Spaces (Docker).
#
# Pré-requis :
#   1. Crée un compte gratuit sur https://huggingface.co
#   2. Crée un Access Token (Settings → Access Tokens → "New token", scope = Write)
#   3. Crée un nouveau Space (https://huggingface.co/new-space) :
#        - SDK : Docker
#        - Hardware : CPU basic (gratuit, 2 vCPU / 16 GB RAM)
#        - Visibility : Public ou Private (tu choisis)
#   4. Note l'identifiant : <username>/<space-name>
#
# Usage :
#   cd .huggingface-space
#   pwsh ./deploy.ps1 -User <username> -Space <space-name> -Token <hf_token>
#
# Le script package web/ + data/ + le Dockerfile dans un git temp, force-push sur le Space.

param(
  [Parameter(Mandatory=$true)] [string]$User,
  [Parameter(Mandatory=$true)] [string]$Space,
  [Parameter(Mandatory=$true)] [string]$Token,
  [string]$Branch = "main"
)

$ErrorActionPreference = 'Stop'

$repoRoot   = Resolve-Path "$PSScriptRoot\.."
$staging    = Join-Path ([IO.Path]::GetTempPath()) ("clipmaker-hf-" + [Guid]::NewGuid().ToString("N").Substring(0,8))
$remoteUrl  = "https://user:${Token}@huggingface.co/spaces/${User}/${Space}"

Write-Host "→ Staging dir : $staging" -ForegroundColor Cyan
New-Item -ItemType Directory -Path $staging | Out-Null

# Copie le Dockerfile + README HF
Copy-Item "$PSScriptRoot\Dockerfile" "$staging\Dockerfile"
Copy-Item "$PSScriptRoot\README.md"  "$staging\README.md"

# Copie le code de l'app (sans node_modules, .next, .env*, uploads, renders, public/music)
$webSrc = Join-Path $repoRoot "web"
$webDst = Join-Path $staging "web"
robocopy $webSrc $webDst /MIR `
  /XD node_modules .next uploads renders `
  /XF .env .env.local .env.development.local .env.production.local *.log `
  | Out-Null

# Nettoie public/music (les pistes seront re-fetchées lazily par vibe)
$musicDst = Join-Path $webDst "public\music"
if (Test-Path $musicDst) {
  Get-ChildItem $musicDst -Recurse -Force | Where-Object { $_.Extension -match '\.(mp3|m4a|aac|wav|ogg)$' } | Remove-Item -Force -ErrorAction SilentlyContinue
}

Push-Location $staging
try {
  git init -q -b $Branch
  git config user.email "deploy@clipmaker.local"
  git config user.name  "clipmaker-deploy"
  git lfs install --local 2>$null
  git add -A
  git commit -q -m "deploy: clipMaker"

  Write-Host "→ Push vers https://huggingface.co/spaces/$User/$Space" -ForegroundColor Cyan
  git remote add origin $remoteUrl
  git push -q --force origin "${Branch}:${Branch}"

  Write-Host ""
  Write-Host "✔ Déployé." -ForegroundColor Green
  Write-Host "  Build/logs : https://huggingface.co/spaces/$User/$Space"
  Write-Host "  URL app    : https://${User}-${Space}.hf.space"
  Write-Host ""
  Write-Host "→ Pense à ajouter GROQ_API_KEY dans Settings → Variables and secrets :"
  Write-Host "  https://huggingface.co/spaces/$User/$Space/settings"
}
finally {
  Pop-Location
  Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}
