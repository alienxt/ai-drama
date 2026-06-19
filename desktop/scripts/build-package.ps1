$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RootDir

$InitText = Get-Content "src\aidrama_desktop\__init__.py" -Raw
$VersionMatch = [regex]::Match($InitText, '__version__ = "([^"]+)"')
$Version = if ($VersionMatch.Success) { $VersionMatch.Groups[1].Value } else { "dev" }

if (-not (Test-Path ".venv")) {
    py -3 -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]" pyinstaller
& ".\.venv\Scripts\pyinstaller.exe" --clean --noconfirm packaging\pyinstaller\ai-drama-desktop.spec

$Archive = "dist\AI-Drama-Desktop-$Version-windows-x64.zip"
if (Test-Path $Archive) {
    Remove-Item $Archive
}
Compress-Archive -Path "dist\AI Drama Desktop\*" -DestinationPath $Archive
Write-Output $Archive
