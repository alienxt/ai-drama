#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
VERSION="${VERSION:-$(python3 -c 'import pathlib,re; text=pathlib.Path("src/aidrama_desktop/__init__.py").read_text(); print(re.search(r"__version__ = \"([^\"]+)\"", text).group(1))' 2>/dev/null || echo dev)}"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]" pyinstaller
pyinstaller --clean --noconfirm packaging/pyinstaller/ai-drama-desktop.spec

if [[ "$(uname -s)" == "Darwin" ]]; then
  DMG="dist/AI-Drama-Desktop-$VERSION.dmg"
  rm -f "$DMG"
  hdiutil create -volname "AI Drama Desktop" -srcfolder "dist/AI Drama Desktop.app" -ov -format UDZO "$DMG"
  echo "$DMG"
else
  ARCHIVE="dist/AI-Drama-Desktop-$VERSION-$(uname -s)-$(uname -m).tar.gz"
  rm -f "$ARCHIVE"
  tar -C dist -czf "$ARCHIVE" "AI Drama Desktop"
  echo "$ARCHIVE"
fi
