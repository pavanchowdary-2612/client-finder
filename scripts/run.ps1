$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$streamlitConfig = Join-Path $repoRoot ".streamlit"
if (-not (Test-Path $streamlitConfig)) {
    New-Item -ItemType Directory -Path $streamlitConfig | Out-Null
}
$env:STREAMLIT_CONFIG_DIR = $streamlitConfig

$python = ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found. Run .\setup.ps1 first."
}
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
    }
    Write-Host "Created .env. Add your API keys and sender settings before using live services."
}

& $python -m streamlit run app.py
