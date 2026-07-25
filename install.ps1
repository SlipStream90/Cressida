# CRESSIDA one-line installer (Windows PowerShell).
#
#   irm https://raw.githubusercontent.com/SlipStream90/Cressida/main/install.ps1 | iex
#
# Clones the repo into %USERPROFILE%\.cressida\src, builds an isolated venv,
# installs CRESSIDA, and wires up the MCP server for Claude Code.
#
# Override via env vars before running: $env:CRESSIDA_BRANCH, $env:CRESSIDA_PROVIDER, etc.
$ErrorActionPreference = "Stop"

$Repo     = if ($env:CRESSIDA_REPO)     { $env:CRESSIDA_REPO }     else { "https://github.com/SlipStream90/Cressida.git" }
$Branch   = if ($env:CRESSIDA_BRANCH)   { $env:CRESSIDA_BRANCH }   else { "main" }
$HomeDir  = if ($env:CRESSIDA_HOME)     { $env:CRESSIDA_HOME }     else { Join-Path $env:USERPROFILE ".cressida" }
$Provider = $env:CRESSIDA_PROVIDER
$Src      = Join-Path $HomeDir "src"
$Venv     = Join-Path $HomeDir "venv"

function Info($m) { Write-Host "[cressida] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[cressida] $m" -ForegroundColor Red; exit 1 }

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Die "git is required." }
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue) }
if (-not $py) { Die "Python 3.11+ is required (python not found)." }
& $py.Source -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)"
if ($LASTEXITCODE -ne 0) { Die "Python 3.11+ is required." }

New-Item -ItemType Directory -Force -Path $HomeDir | Out-Null
if (Test-Path (Join-Path $Src ".git")) {
    Info "Updating checkout at $Src"
    git -C $Src fetch --depth 1 origin $Branch
    git -C $Src checkout -q $Branch
    git -C $Src reset -q --hard "origin/$Branch"
} else {
    Info "Cloning $Repo ($Branch)"
    git clone --branch $Branch --depth 1 $Repo $Src
}

Info "Creating virtualenv at $Venv"
& $py.Source -m venv $Venv
$VPy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $VPy)) { $VPy = Join-Path $Venv "bin/python" }  # non-Windows layout

& $VPy -m pip install --quiet --upgrade pip
$Target = $Src
if ($Provider) { $Target = "$Src[$Provider]" }
Info "Installing CRESSIDA$(if ($Provider) { " (+$Provider)" })"
& $VPy -m pip install --quiet -e $Target

Info "Wiring up the MCP server"
& $VPy (Join-Path $Src "onboard.py") --skip-install --register

Info "Done. Installed at $HomeDir"
Write-Host "  CLI:    $(Join-Path $Venv 'Scripts\cressida.exe') run brief.md"
Write-Host "  MCP:    restart Claude Code, then call the cressida_status tool"
Write-Host "  Update: re-run this installer any time (it pulls the latest and reinstalls)"
