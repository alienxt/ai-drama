# Build from the repository root:
#   cd desktop
#   pyinstaller packaging/pyinstaller/ai-drama-desktop.spec

from pathlib import Path
import sys


project_root = Path.cwd()
src_root = project_root / "src"
assets_dir = src_root / "aidrama_desktop" / "assets"
icon_path = assets_dir / ("app-icon.ico" if sys.platform.startswith("win") else "app-icon.icns")


a = Analysis(
    [str(src_root / "aidrama_desktop" / "gui" / "app.py")],
    pathex=[str(src_root)],
    binaries=[],
    datas=[(str(assets_dir), "aidrama_desktop/assets")],
    hiddenimports=[],
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
            "NSHighResolutionCapable": "True",
        },
    )
