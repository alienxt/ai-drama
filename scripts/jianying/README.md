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
  --clip-count 24 \
  --overwrite
```

Inputs:

- `--video`: required source episode video.
- `--srt`: optional subtitle file. SRT timestamps become Jianying text segments.
- `--bgm`: optional BGM file. Can be repeated; files become audio materials and timeline segments.

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
- Windows: launches Jianying/CapCut, maximizes and brings the window forward with PowerShell/User32, returns to the Home page, double-clicks the first draft thumbnail, then captures only the Jianying/CapCut main window rectangle.

Pass `--full-screen-capture` only when you intentionally need the entire desktop screenshot.

## App overrides

Default app candidates:

- macOS: `/Applications/VideoFusion-macOS.app`, `/Applications/剪映专业版.app`, `/Applications/JianyingPro.app`, `/Applications/CapCut.app`
- Windows: common JianyingPro and CapCut install paths under `%LOCALAPPDATA%`, `%ProgramFiles%`, and `%ProgramFiles(x86)%`

Override with `--jianying-app` or `JIANYING_APP` when needed.
