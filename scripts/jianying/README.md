# Jianying project tool

`create-jianying-project.js` is the formal Jianying/CapCut draft generator. Given a local video, optional SRT subtitles, and optional BGM files, it creates a desktop draft, registers it in Jianying's draft index, and can optionally open the editor and save a proof screenshot.

The generated draft intentionally uses a richer proof timeline: uneven video clips, partial speed edits, staggered BGM on multiple audio tracks, subtitles, and auxiliary text tracks named like filters/effects/stickers/project markers. This makes the proof screenshot closer to a real editing project instead of a flat one-track template.

It uses only Node.js built-ins plus local `ffmpeg`/`ffprobe`, so the same script can run on macOS and Windows.

## Basic usage

```bash
node scripts/jianying/create-jianying-project.js \
  --video "/path/to/episode.mp4" \
  --srt "/path/to/subtitles.srt" \
  --bgm "/path/to/bgm.mp3" \
  --name "剧名_第99集_剪辑工程" \
  --template "/path/to/template-draft" \
  --strategy "platform-safe-v1" \
  --clip-count 24 \
  --overwrite
```

Inputs:

- `--video`: required source episode video.
- `--srt`: optional subtitle file. SRT timestamps become Jianying text segments.
- `--bgm`: optional BGM file. Can be repeated; files become audio materials and timeline segments.
- `--template`: optional explicit clean template draft. If omitted, the tool creates a built-in clean seed draft.
- `--strategy`: optional timeline proof strategy. Built-ins include `platform-safe-v1`（平台安全工程）, `layered-proof-v1`（标准分轨工程）, and `competitor-native-v1`（竞品原生工程）. The desktop runner exposes all three and chooses one per drama when no specific strategy is requested.

Strategy policy:

- Multiple strategy templates can coexist in the tool.
- `platform-safe-v1` is the audit-safe default: one main video track, one subtitle track, clip-matched original audio, at most one music bed, one light native color track, and hidden audio cards in the media panel.
- `competitor-native-v1` mirrors a competitor-style native proof layout: 5 media-pool video clips, 10 V1 timeline cuts, clip-matched original audio, 3 staggered music tracks, hidden imported subtitle text, native filter/effect/sticker tracks, and hidden audio cards in the media panel.
- Each generated proof draft records `strategy_id` and `strategy_label` in `codex_audit.json` and `jianying_project_result.json`.
- The desktop runner writes the chosen strategy into `.jianying-project-materials.json`, so cached screenshots are reused only when the capture version and requested strategy match.

Template policy:

- A dedicated `AI_DRAMA_TEMPLATE_DRAFT` is no longer used by default. Pass it via `--template` only when you intentionally want an external compatibility template.
- The built-in seed contains no drama title, media path, backup, or Jianying runtime cache.
- The tool no longer automatically uses ordinary business drafts as templates, because copied Jianying cache files can carry old drama media references into the new draft.
- `--allow-draft-template-fallback` exists only for manual debugging. Do not enable it on production clients.

Outputs:

- Jianying/CapCut draft directory under the desktop draft root.
- `codex_audit.json` inside the generated draft.
- `jianying_project_result.json` inside `--output-dir`.
- Optional Jianying/CapCut window screenshot PNG when `--capture` or `--screenshot` is provided.

## Default draft roots

- macOS: `~/Movies/JianyingPro/User Data/Projects/com.lveditor.draft`
- Windows: `%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft`

If your install uses another location, pass `--draft-root` or set `JIANYING_DRAFT_ROOT`.

## Screenshot proof

```bash
node scripts/jianying/create-jianying-project.js \
  --video "/path/to/episode.mp4" \
  --srt "/path/to/subtitles.srt" \
  --bgm "/path/to/bgm.mp3" \
  --name "剧名_第99集_剪辑工程" \
  --overwrite \
  --open \
  --open-draft \
  --capture
```

`--open-draft` is best-effort UI automation:

- macOS: launches Jianying, activates the app by bundle id, normalizes the window size, returns to the Home page, double-clicks the first draft thumbnail, then captures only the Jianying window bounds with `screencapture -R`. The terminal/Codex host app needs Accessibility/Automation permission.
- Windows: requires Jianying 6 or below and recommends `5.9.0.11632`. The Windows desktop package includes the same `uiautomation` library used by pyJianYingDraft. Its hidden helper waits for the Jianying window, recognizes it by process path/name, title, or known Jianying/CapCut tokens, searches `TextControl` at depth 2, reads property `FullDescription` (`30159`) directly, matches `HomePageDraftTitle:<full draft name>` exactly, clicks the title control's parent card with `simulateMove=False`, and accepts editor success by a MainWindow class or a draft-title window match. Jianying 7 or above is rejected before launch because it no longer exposes the required legacy controls. There is no OCR, truncated-title, or fixed-coordinate fallback.

Configure the legacy Windows executable with `--jianying-app`, `JIANYING_APP`, or the desktop client's “剪映程序地址” setting. Versioned Jianying installations under common `Apps/<version>` directories are detected automatically, with `5.9.0.11632` preferred.

Pass `--full-screen-capture` only when you intentionally need the entire desktop screenshot.

## Windows open diagnostics

The packaged Windows desktop supplies its bundled Python UIA helper automatically. When running this script directly from the source tree, first point it at a Python environment that contains `uiautomation`:

```powershell
$env:AIDRAMA_JIANYING_UIA_HELPER_COMMAND='["C:\\path\\to\\python.exe","-m","aidrama_desktop.gui.app","--jianying-uia-helper"]'
```

Then use this standalone mode on a Windows desktop session when the draft is created but the editor does not open:

```powershell
node scripts\jianying\create-jianying-project.js `
  --debug-windows-open `
  --name "剧名_第99集_剪辑工程" `
  --output-dir "C:\jy-open-debug" `
  --jianying-app "C:\Users\Administrator\AppData\Local\JianyingPro\JianyingPro.exe"
```

It does not create a draft and does not require `--video`. It reuses the production named-draft UI Automation path and writes `windows_open_debug.json`, `before-open.png`, and `after-open.png` to `--output-dir`. The report includes the UIA action log, editor-detection signals, process/window snapshots, and screenshots. If `--name` is omitted, it tries to use the newest draft from `--draft-root` / `JIANYING_DRAFT_ROOT`.

## App overrides

Default app candidates:

- macOS: `/Applications/VideoFusion-macOS.app`, `/Applications/剪映专业版.app`, `/Applications/JianyingPro.app`, `/Applications/CapCut.app`
- Windows: common JianyingPro and CapCut install paths under `%LOCALAPPDATA%`, `%ProgramFiles%`, and `%ProgramFiles(x86)%`

Override with `--jianying-app` or `JIANYING_APP` when needed.
