# Build from the repository root:
#   cd desktop
#   pyinstaller packaging/pyinstaller/ai-drama-desktop.spec

from pathlib import Path
import re
import sys


project_root = Path.cwd()
repo_root = project_root.parent
src_root = project_root / "src"
assets_dir = src_root / "aidrama_desktop" / "assets"
jianying_tool = repo_root / "scripts" / "jianying" / "create-jianying-project.js"
icon_path = assets_dir / ("app-icon.ico" if sys.platform.startswith("win") else "app-icon.icns")
init_text = (src_root / "aidrama_desktop" / "__init__.py").read_text(encoding="utf-8")
version_match = re.search(r'__version__ = "([^"]+)"', init_text)
app_version = version_match.group(1) if version_match else "0.0.0"


a = Analysis(
    [str(src_root / "aidrama_desktop" / "gui" / "app.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=[
        (str(assets_dir), "aidrama_desktop/assets"),
        (str(jianying_tool), "aidrama_desktop/tools/jianying"),
    ],
    hiddenimports=["uiautomation"] if sys.platform.startswith("win") else [],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Drama Desktop",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI Drama Desktop",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="AI Drama Desktop.app",
        icon=str(icon_path),
        bundle_identifier="com.onehot.aidrama.desktop",
        info_plist={
            "CFBundleDisplayName": "AI Drama Desktop",
            "CFBundleName": "AI Drama Desktop",
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "NSHighResolutionCapable": "True",
        },
    )
