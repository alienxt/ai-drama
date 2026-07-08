[CmdletBinding()]
param(
    [switch]$SkipInstaller,
    [switch]$SkipZip,
    [string]$InnoSetupCompiler = $env:INNO_SETUP_COMPILER
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$IsWindowsHost = [System.Environment]::OSVersion.Platform -eq "Win32NT"
if (-not $IsWindowsHost) {
    throw "Windows packaging must be run on Windows. Use scripts/build-package.sh for macOS/Linux."
}

function New-WindowsVenvIfNeeded {
    $venvDir = Join-Path $RootDir ".venv-windows"
    $venvPython = Join-Path $venvDir "Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv $venvDir
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv $venvDir
    } else {
        throw "Python 3.11+ was not found. Install Python first, then rerun this script."
    }

    if (-not (Test-Path $venvPython)) {
        throw "Failed to create Windows virtual environment at $venvDir."
    }
    return $venvPython
}

function Resolve-InnoSetupCompiler {
    param([string]$RequestedPath)

    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return (Resolve-Path $RequestedPath).Path
    }

    $command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

$InitText = Get-Content "src\aidrama_desktop\__init__.py" -Raw
$VersionMatch = [regex]::Match($InitText, '__version__ = "([^"]+)"')
$Version = if ($VersionMatch.Success) { $VersionMatch.Groups[1].Value } else { "dev" }

$VenvPython = New-WindowsVenvIfNeeded
$VenvScripts = Split-Path $VenvPython -Parent
$PyInstaller = Join-Path $VenvScripts "pyinstaller.exe"

Write-Host "Installing desktop build dependencies..."
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[dev]" pyinstaller

Write-Host "Building Windows desktop app..."
& $PyInstaller --clean --noconfirm packaging\pyinstaller\ai-drama-desktop.spec

$DistDir = Join-Path $RootDir "dist\AI Drama Desktop"
$OutputDir = Join-Path $RootDir "dist"
$ExePath = Join-Path $DistDir "AI Drama Desktop.exe"
if (-not (Test-Path $ExePath)) {
    throw "PyInstaller finished, but the Windows executable was not found at $ExePath."
}

$Artifacts = @()

if (-not $SkipZip) {
    $Archive = Join-Path $RootDir "dist\AI-Drama-Desktop-$Version-windows-x64.zip"
    if (Test-Path $Archive) {
        Remove-Item $Archive -Force
    }
    Write-Host "Creating portable zip..."
    Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $Archive
    $Artifacts += $Archive
}

if (-not $SkipInstaller) {
    $Compiler = Resolve-InnoSetupCompiler $InnoSetupCompiler
    if (-not $Compiler) {
        throw "Inno Setup 6 was not found. Install it from https://jrsoftware.org/isinfo.php or set INNO_SETUP_COMPILER to ISCC.exe. Use -SkipInstaller to only build the portable zip."
    }

    $InstallerPath = Join-Path $RootDir "dist\AI-Drama-Desktop-Setup-$Version-windows-x64.exe"
    if (Test-Path $InstallerPath) {
        Remove-Item $InstallerPath -Force
    }

    Write-Host "Creating Windows installer..."
    & $Compiler `
        "/DAppVersion=$Version" `
        "/DSourceDir=$DistDir" `
        "/DOutputDir=$OutputDir" `
        "packaging\windows\ai-drama-desktop.iss"

    if (-not (Test-Path $InstallerPath)) {
        throw "Inno Setup finished, but the installer was not found at $InstallerPath."
    }
    $Artifacts += $InstallerPath
}

Write-Host ""
Write-Host "Build artifacts:"
foreach ($Artifact in $Artifacts) {
    Write-Output $Artifact
}
