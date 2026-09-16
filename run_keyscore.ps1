$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv64\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到 64 位虚拟环境。请先按 README.md 安装依赖。"
}

$env:PYTHONPATH = Join-Path $projectRoot "src"
$env:KEYSCORE_DATA_DIR = Join-Path $projectRoot "data"
& $pythonPath (Join-Path $projectRoot "main.py")
