[CmdletBinding()]
param([string]$Python = "python", [string]$OllamaModel = "qwen2.5vl:7b")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
function Fail([string]$Message) { throw "ShortsPipeline installer: $Message" }
function Assert-LastExit([string]$Message) { if ($LASTEXITCODE -ne 0) { Fail $Message } }

& $Python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
Assert-LastExit "Python 3.11+ is required. Specify -Python if needed."
$Venv = Join-Path $Root ".venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $VenvPython)) { & $Python -m venv $Venv; Assert-LastExit "Could not create the project-local .venv." }
& $VenvPython -m pip install --upgrade pip; Assert-LastExit "Could not upgrade pip in .venv."
& $VenvPython -m pip install -r (Join-Path $Root "requirements.txt"); Assert-LastExit "Could not install requirements into .venv."
& $VenvPython -m pip install -e $Root; Assert-LastExit "Could not install ShortsPipeline in editable mode."
& $VenvPython -c "import yt_dlp"; Assert-LastExit "yt-dlp was not installed inside .venv."

foreach ($tool in @("ffmpeg", "ffprobe")) { if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { Fail "$tool is required on PATH." } }
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { & nvidia-smi --query-gpu=name,driver_version --format=csv,noheader; Assert-LastExit "nvidia-smi could not verify the GPU/CUDA runtime." } else { Write-Warning "nvidia-smi is unavailable; GPU/CUDA cannot be verified." }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Fail "Ollama is required. Install/start it, then run: ollama pull $OllamaModel" }
$Models = & ollama list; Assert-LastExit "Ollama is installed but unavailable. Start its service and retry."
if (-not (($Models | Select-Object -Skip 1) -match "^$([regex]::Escape($OllamaModel))\s")) { Fail "Required Ollama model is missing: $OllamaModel. Run: ollama pull $OllamaModel" }

New-Item -ItemType Directory -Force -Path (Join-Path $Root "workspace\downloads"), (Join-Path $Root "workspace\tmp") | Out-Null
Write-Output "Installed in $Venv. Activate with: $Venv\Scripts\Activate.ps1"