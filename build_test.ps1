$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $projectRoot ".venv64\Scripts\python.exe"
$outputDirectory = Join-Path $projectRoot "dist\KeyScore-Test"
$applicationDataDirectory = Join-Path $outputDirectory "data"
$assetsDirectory = Join-Path $projectRoot "src\keyscore\assets"
$iconPath = Join-Path $assetsDirectory "KS.ico"
$originalPath = $env:PATH

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "未找到项目虚拟环境：$pythonPath"
}

& $pythonPath -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "未安装 PyInstaller，请先执行：.\.venv64\Scripts\python.exe -m pip install 'pyinstaller>=6,<7'"
}

Push-Location $projectRoot
try {
    $basePythonDirectory = & $pythonPath -c "import sys; print(sys.base_prefix)"
    $safePathEntries = @(
        (Split-Path -Parent $pythonPath),
        $basePythonDirectory,
        (Join-Path $basePythonDirectory "DLLs"),
        (Join-Path $env:SystemRoot "System32"),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot "System32\Wbem")
    )
    $env:PATH = $safePathEntries -join [System.IO.Path]::PathSeparator

    & $pythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --windowed `
        --onedir `
        --name "KeyScore-Test" `
        --icon "$iconPath" `
        --add-data "$assetsDirectory;keyscore\assets" `
        --specpath "build" `
        --paths "src" `
        --exclude-module "PySide6.QtMultimedia" `
        --exclude-module "PySide6.QtNetwork" `
        --exclude-module "PySide6.QtOpenGL" `
        --exclude-module "PySide6.QtPdf" `
        --exclude-module "PySide6.QtQml" `
        --exclude-module "PySide6.QtQuick" `
        --exclude-module "PySide6.QtWebEngineCore" `
        --exclude-module "tkinter" `
        "main.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller 构建失败，退出码：$LASTEXITCODE"
    }

    New-Item -ItemType Directory -Force -Path $applicationDataDirectory | Out-Null
    Copy-Item -Recurse -Force -LiteralPath (Join-Path $projectRoot "data\profiles") -Destination $applicationDataDirectory
    Copy-Item -Recurse -Force -LiteralPath (Join-Path $projectRoot "data\scores") -Destination $applicationDataDirectory

    $qtDirectory = Join-Path $outputDirectory "_internal\PySide6"
    $resolvedOutputDirectory = [System.IO.Path]::GetFullPath($outputDirectory)
    $resolvedQtDirectory = [System.IO.Path]::GetFullPath($qtDirectory)
    $outputPrefix = $resolvedOutputDirectory + [System.IO.Path]::DirectorySeparatorChar
    if (-not $resolvedQtDirectory.StartsWith($outputPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Qt 目录不在构建输出目录内，已停止清理：$resolvedQtDirectory"
    }

    $unusedPluginDirectories = @(
        "plugins\generic",
        "plugins\iconengines",
        "plugins\imageformats",
        "plugins\platforminputcontexts"
    )
    foreach ($relativePath in $unusedPluginDirectories) {
        $targetPath = Join-Path $qtDirectory $relativePath
        if (Test-Path -LiteralPath $targetPath) {
            Remove-Item -Recurse -Force -LiteralPath $targetPath
        }
    }

    $platformsDirectory = Join-Path $qtDirectory "plugins\platforms"
    Get-ChildItem -LiteralPath $platformsDirectory -File |
        Where-Object Name -ne "qwindows.dll" |
        Remove-Item -Force

    $unusedQtLibraries = @(
        "opengl32sw.dll",
        "Qt6Network.dll",
        "Qt6OpenGL.dll",
        "Qt6Pdf.dll",
        "Qt6Qml.dll",
        "Qt6QmlMeta.dll",
        "Qt6QmlModels.dll",
        "Qt6QmlWorkerScript.dll",
        "Qt6Quick.dll",
        "Qt6Svg.dll",
        "Qt6VirtualKeyboard.dll"
    )
    foreach ($libraryName in $unusedQtLibraries) {
        $libraryPath = Join-Path $qtDirectory $libraryName
        if (Test-Path -LiteralPath $libraryPath) {
            Remove-Item -Force -LiteralPath $libraryPath
        }
    }

    $internalDirectory = Join-Path $outputDirectory "_internal"
    Get-ChildItem -LiteralPath $internalDirectory -File -Filter "icu*.dll" |
        Remove-Item -Force

    $translationsDirectory = Join-Path $qtDirectory "translations"
    Get-ChildItem -LiteralPath $translationsDirectory -File |
        Where-Object Name -notin @("qt_zh_CN.qm", "qtbase_zh_CN.qm") |
        Remove-Item -Force
}
finally {
    $env:PATH = $originalPath
    Pop-Location
}

Write-Host "测试版已生成：$outputDirectory"
