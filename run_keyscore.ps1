$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv64\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "The 64-bit virtual environment was not found. Follow README.md to install dependencies."
}

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:KEYSCORE_DATA_DIR = Join-Path $projectRoot "data"
& $pythonPath (Join-Path $projectRoot "main.py")
