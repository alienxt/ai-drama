#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any


DEFAULT_VIEWPORT_WIDTH = 1470
DEFAULT_VIEWPORT_HEIGHT = 835
DEFAULT_DEVICE_SCALE_FACTOR = 2
DEFAULT_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
MATERIAL_MANIFEST_NAME = "分镜材料清单.json"
DEFAULT_DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro"
DEFAULT_STYLE = "真人风格-国产都市"
DEFAULT_MEDIA_ACCOUNT_NAME = "用户1182"
COSTUME_STYLE = "真人风格-古代"
DEFAULT_RANDOM_TARGET_SHOTS_MIN = 15
DEFAULT_RANDOM_TARGET_SHOTS_MAX = 20
DEFAULT_SCREENSHOT_COUNT = 3
SUMMARY_MIN_CHARS = 150
SUMMARY_MAX_CHARS = 300
COSTUME_STYLE_KEYWORDS = (
    "古风",
    "古代",
    "穿越",
    "旧朝",
    "东宫",
    "宫",
    "皇",
    "帝",
    "王爷",
    "王妃",
    "太子",
    "公主",
    "将军",
    "侯府",
    "世子",
    "殿下",
    "陛下",
    "娘娘",
    "江湖",
    "剑",
    "仙",
    "修仙",
    "玄幻",
    "宗门",
    "灵根",
    "长生",
    "圣杖",
)


@dataclass(frozen=True)
class RenderPaths:
    output_dir: Path
    keyframes_dir: Path
    pages_dir: Path
    screenshots_dir: Path


def main() -> None:
    args = parse_args()
    material_dir = args.material_dir.expanduser().resolve() if args.material_dir else None
    storyboard_path = (
        args.storyboard.expanduser().resolve()
        if args.storyboard
        else material_dir / "storyboard.json"
        if material_dir
        else None
    )
    video_path = (
        args.video.expanduser().resolve()
        if args.video
        else material_dir / "episodes-11-15.mp4"
        if material_dir
        else None
    )
    if not video_path:
        raise SystemExit("请通过 --video 指定 MP4，或通过 --material-dir 指定包含视频的材料目录。")
    manifest_path = material_dir / MATERIAL_MANIFEST_NAME if material_dir else None

    if not video_path.exists():
        raise SystemExit(f"找不到视频文件：{video_path}")

    ffmpeg_path = resolve_executable(args.ffmpeg_path, "ffmpeg")
    chrome_path = resolve_chrome_path(args.chrome_path)

    manifest = load_json(manifest_path) if manifest_path and manifest_path.exists() else {}
    if storyboard_path and storyboard_path.exists():
        storyboard = load_json(storyboard_path)
    else:
        storyboard = build_storyboard_from_video(
            ffmpeg_path,
            video_path,
            segment_seconds=args.segment_seconds,
            target_shots=args.target_shots,
            media_account=args.media_account,
            points_balance=args.points_balance,
            style=args.style,
        )
    shots = storyboard.get("shots") or []
    if not shots:
        raise SystemExit("没有可渲染的分镜。")

    paths = prepare_output_paths(args.output_dir.expanduser().resolve())

    if args.deepseek:
        storyboard = enrich_storyboard_with_deepseek(
            storyboard=storyboard,
            model=args.deepseek_model,
            api_base=args.deepseek_api_base,
            api_key=os.environ.get("DEEPSEEK_API_KEY"),
            log_path=paths.output_dir / "deepseek-call-log.json",
        )
        shots = storyboard.get("shots") or []

    selected_shots = parse_selected_shots(args.shots, manifest, len(shots), args.screenshot_count)
    viewport = {
        "width": int((manifest.get("viewport") or {}).get("width") or DEFAULT_VIEWPORT_WIDTH),
        "height": int((manifest.get("viewport") or {}).get("height") or DEFAULT_VIEWPORT_HEIGHT),
        "deviceScaleFactor": float(
            (manifest.get("viewport") or {}).get("deviceScaleFactor") or DEFAULT_DEVICE_SCALE_FACTOR
        ),
    }

    extract_keyframes(ffmpeg_path, video_path, shots, paths.keyframes_dir)
    (paths.output_dir / "storyboard.generated.json").write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    screenshots = render_screenshots(
        chrome_path=chrome_path,
        storyboard=storyboard,
        selected_shots=selected_shots,
        paths=paths,
        viewport=viewport,
    )

    print("已生成分镜截图：")
    for screenshot in screenshots:
        print(screenshot)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render storyboard workbench screenshots from local materials.")
    parser.add_argument(
        "--material-dir",
        type=Path,
        help="包含 storyboard.json、episodes-11-15.mp4、分镜材料清单.json 的材料目录。",
    )
    parser.add_argument("--storyboard", type=Path, help="storyboard.json 路径，默认使用 material-dir/storyboard.json。")
    parser.add_argument("--video", type=Path, help="MP4 视频路径，默认使用 material-dir/episodes-11-15.mp4。")
    parser.add_argument(
        "--shots",
        default="",
        help="要截图的分镜编号，逗号分隔；传 all 生成全部；默认读取清单，否则随机抽 3 张。",
    )
    parser.add_argument(
        "--segment-seconds",
        type=float,
        help="无 storyboard 时按固定秒数切分；不传时默认随机生成 15-20 个分镜段。",
    )
    parser.add_argument(
        "--target-shots",
        type=int,
        help="无 storyboard 时固定生成的分镜数量；设置后优先于 --segment-seconds。",
    )
    parser.add_argument(
        "--screenshot-count",
        type=int,
        default=DEFAULT_SCREENSHOT_COUNT,
        help="未指定 --shots 且清单无截图配置时随机生成的工程截图数量，默认 3。",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/storyboard-preview"),
        help="输出目录，默认 output/storyboard-preview。",
    )
    parser.add_argument("--media-account", default="", help="截图顶部显示的媒体号/用户名；不传则显示用户1182。")
    parser.add_argument("--points-balance", default="", help="截图顶部显示的积分余额；为空则按任务随机。")
    parser.add_argument("--style", default="", help="截图顶部显示的风格；不传则根据视频名推断。")
    parser.add_argument("--deepseek", action="store_true", help="调用 DeepSeek 补全分镜标题、概要和画面要素。")
    parser.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_MODEL, help="DeepSeek 模型名。")
    parser.add_argument("--deepseek-api-base", default=DEFAULT_DEEPSEEK_API_BASE, help="DeepSeek API base URL。")
    parser.add_argument("--ffmpeg-path", default="ffmpeg", help="ffmpeg 可执行文件路径。")
    parser.add_argument("--chrome-path", default=DEFAULT_CHROME_PATH, help="Chrome 可执行文件路径。")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exception:
        raise SystemExit(f"找不到 JSON 文件：{path}") from exception
    except json.JSONDecodeError as exception:
        raise SystemExit(f"JSON 格式错误：{path}: {exception}") from exception


def parse_selected_shots(raw: str, manifest: dict[str, Any], total_shots: int, screenshot_count: int) -> list[int]:
    if raw.strip():
        if raw.strip().lower() == "all":
            return list(range(1, total_shots + 1))
        return [int(part.strip()) for part in raw.split(",") if part.strip()]
    if screenshot_count <= 0:
        raise SystemExit("--screenshot-count 必须大于 0。")
    manifest_screenshots = manifest.get("screenshots") or []
    selected = [int(item["shotIndex"]) for item in manifest_screenshots if item.get("shotIndex")]
    if selected:
        return [index for index in selected if 1 <= index <= total_shots]
    return sample_shot_indexes(total_shots, screenshot_count)


def sample_shot_indexes(total_shots: int, count: int = DEFAULT_SCREENSHOT_COUNT) -> list[int]:
    if total_shots <= 0 or count <= 0:
        return []
    sample_size = min(total_shots, count)
    return sorted(random.sample(range(1, total_shots + 1), sample_size))


def build_storyboard_from_video(
    ffmpeg_path: str,
    video_path: Path,
    *,
    segment_seconds: float | None,
    target_shots: int | None,
    media_account: str,
    points_balance: str,
    style: str,
) -> dict[str, Any]:
    if segment_seconds is not None and segment_seconds <= 0:
        raise SystemExit("--segment-seconds 必须大于 0。")
    probe = probe_video(ffmpeg_path, video_path)
    duration = float(probe.get("duration") or 0)
    if duration <= 0:
        raise SystemExit(f"无法读取视频时长：{video_path}")
    width = int(probe.get("width") or 720)
    height = int(probe.get("height") or 1280)
    fps = float(probe.get("fps") or 30)
    aspect_ratio = aspect_ratio_label(width, height)
    title, episode_label, episode_number = infer_title_and_episode(video_path)
    style = infer_storyboard_style(title=title, configured_style=style)
    if target_shots is not None and target_shots <= 0:
        raise SystemExit("--target-shots 必须大于 0。")
    if target_shots:
        total = target_shots
    elif segment_seconds:
        total = max(1, math.ceil(duration / segment_seconds))
    else:
        total = random.randint(DEFAULT_RANDOM_TARGET_SHOTS_MIN, DEFAULT_RANDOM_TARGET_SHOTS_MAX)
    actual_segment_seconds = duration / total
    shots = []
    for offset in range(total):
        start = round(offset * actual_segment_seconds, 3)
        end = round(duration if offset == total - 1 else (offset + 1) * actual_segment_seconds, 3)
        index = offset + 1
        shot_duration = max(0.1, round(end - start, 3))
        shots.append(
            {
                "id": f"video-only-shot-{index:03d}",
                "index": index,
                "title": f"1-{index} 自动分镜",
                "start": start,
                "end": end,
                "startTimecode": seconds_to_timecode(start),
                "endTimecode": seconds_to_timecode(end),
                "durationSeconds": shot_duration,
                "summary": "已根据视频时长自动切分；剧情摘要、人物、场景和镜头语言将在第二步分析后补全。",
                "characters": [],
                "scene": [],
                "props": [],
                "shotSize": "中景",
                "cameraAngle": "平视",
                "cameraMotion": "固定",
                "dialogues": [],
                "mode": "reference-video",
                "prompt": "",
                "model": "Seedance 2.0",
                "aspectRatio": aspect_ratio,
                "duration": int(round(shot_duration)),
                "resolution": f"{width} × {height}",
                "fps": int(round(fps)),
                "assets": [{"type": "keyframe", "path": f"keyframes/shot-{index:03d}.jpg"}],
                "keyframe": f"keyframes/shot-{index:03d}.jpg",
                "sourceEpisode": episode_number,
                "sourceStart": start,
                "sourceEnd": end,
                "sourceStartTimecode": seconds_to_timecode(start),
                "sourceEndTimecode": seconds_to_timecode(end),
                "inferenceOnly": False,
            }
        )
    return {
        "version": 1,
        "drama": {
            "title": title,
            "sourceTitle": title,
            "episodeNumber": episode_number,
            "endEpisodeNumber": episode_number,
        },
        "episode": {"title": episode_label, "startEpisode": episode_number, "endEpisode": episode_number},
        "source": {"video": str(video_path), "duration": duration, "width": width, "height": height, "fps": fps},
        "totalShots": len(shots),
        "workspace": {
            "scriptName": title,
            "episodeLabel": episode_label,
            "style": style,
            "username": media_account or DEFAULT_MEDIA_ACCOUNT_NAME,
            "pointsBalance": points_balance or random_points_balance(),
            "promptPoints": 0.056,
            "generationPoints": 151,
            "resolution": f"{width} × {height}",
            "fps": int(round(fps)),
        },
        "deepseekInference": {"status": "not-started", "inferredShots": 0},
        "shots": shots,
    }


def random_points_balance() -> str:
    return f"{random.uniform(2000, 18000):.3f}"


def infer_storyboard_style(*, title: str = "", summary: str = "", configured_style: str = "") -> str:
    configured = str(configured_style or "").strip()
    if configured and configured != DEFAULT_STYLE:
        return configured
    text = f"{title or ''} {summary or ''}".lower()
    if any(keyword.lower() in text for keyword in COSTUME_STYLE_KEYWORDS):
        return COSTUME_STYLE
    return configured or DEFAULT_STYLE


def enrich_storyboard_with_deepseek(
    *,
    storyboard: dict[str, Any],
    model: str,
    api_base: str,
    api_key: str | None,
    log_path: Path,
) -> dict[str, Any]:
    if not api_key:
        raise SystemExit("缺少 DeepSeek API Key。请设置环境变量 DEEPSEEK_API_KEY，或传 --deepseek-api-key。")
    request_payload = build_deepseek_storyboard_request(storyboard, model)
    response_payload = call_deepseek_chat_completions(api_base, api_key, request_payload)
    content = deepseek_message_content(response_payload)
    parsed = parse_json_object(content)
    merged = merge_deepseek_storyboard(storyboard, parsed, model)
    write_deepseek_log(log_path, request_payload, response_payload, parsed)
    return merged


def build_deepseek_storyboard_request(storyboard: dict[str, Any], model: str) -> dict[str, Any]:
    drama = storyboard.get("drama") or {}
    episode = storyboard.get("episode") or {}
    source = storyboard.get("source") or {}
    workspace = storyboard.get("workspace") or {}
    shots = storyboard.get("shots") or []
    compact_shots = [
        {
            "index": shot.get("index"),
            "startTimecode": shot.get("startTimecode"),
            "endTimecode": shot.get("endTimecode"),
            "durationSeconds": shot.get("durationSeconds"),
        }
        for shot in shots
    ]
    system_prompt = (
        "你是短剧分镜导演和 AIGC 视频提示词策划。"
        "你需要根据剧名、剧集、视频时长和分镜时间轴，生成可用于分镜工作台展示的结构化中文 JSON。"
        "如果没有字幕或视觉识别结果，不要假装已经看见画面；可以基于剧名、类型和时间轴给出保守、通用但可用的分镜文案。"
        "只输出 JSON，不要输出 Markdown。"
    )
    user_prompt = {
        "task": "补全 storyboard shots 的展示字段",
        "constraints": [
            "输出必须是一个 JSON object。",
            "shots 数量必须与输入一致，index 必须一一对应。",
            "title 控制在 4-8 个中文字符，最终页面会自动加 1-index 前缀时也要自然。",
            f"summary 控制在 {SUMMARY_MIN_CHARS}-{SUMMARY_MAX_CHARS} 个中文字符，至少达到原合格长度的 5 倍；"
            "重点补足人物状态、动作推进、环境氛围、镜头关系和剧情张力。",
            "characters、scene、props 都输出字符串数组；不知道时可以输出空数组。",
            "shotSize 只能从：全景、中景、中近景、近景、特写 里选。",
            "cameraAngle 只能从：平视、俯视、仰视、侧面 里选。",
            "cameraMotion 只能从：固定、手持、推镜、拉镜、跟拍 里选。",
            "dialogues 可以为空数组；没有转写时不要编造具体对白。",
            "inferredPrompt 用一句适合视频生成模型的中文提示词。",
        ],
        "input": {
            "dramaTitle": drama.get("title") or drama.get("sourceTitle"),
            "episodeLabel": episode.get("title"),
            "style": workspace.get("style"),
            "source": {
                "duration": source.get("duration"),
                "width": source.get("width"),
                "height": source.get("height"),
                "fps": source.get("fps"),
            },
            "shots": compact_shots,
        },
        "outputSchema": {
            "episodeContext": {
                "episodeSummary": "本集整体剧情概述",
                "characters": [{"name": "人物名", "role": "人物作用"}],
                "sceneCandidates": ["场景"],
            },
            "shots": [
                {
                    "index": 1,
                    "title": "分镜标题",
                    "summary": "150-300字分镜概要",
                    "characters": ["人物"],
                    "scene": ["场景"],
                    "props": ["道具"],
                    "speaker": "",
                    "shotSize": "中景",
                    "cameraAngle": "平视",
                    "cameraMotion": "固定",
                    "action": "动作描述",
                    "emotion": "情绪",
                    "dialogues": [{"speaker": "", "text": ""}],
                    "inferredPrompt": "提示词",
                    "reviewRequired": ["需要人工确认的问题"],
                }
            ],
        },
    }
    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
    }


def call_deepseek_chat_completions(api_base: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = api_base.rstrip("/") + "/chat/completions"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exception:
        detail = exception.read().decode("utf-8", errors="replace")
        raise SystemExit(f"DeepSeek 请求失败：HTTP {exception.code}\n{detail}") from exception
    except urllib.error.URLError as exception:
        raise SystemExit(f"DeepSeek 请求失败：{exception.reason}") from exception
    except json.JSONDecodeError as exception:
        raise SystemExit(f"DeepSeek 响应不是合法 JSON：{exception}") from exception


def deepseek_message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices") or []
    if not choices:
        raise SystemExit("DeepSeek 响应缺少 choices。")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise SystemExit("DeepSeek 响应缺少 message.content。")
    return content


def parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise SystemExit("DeepSeek 输出必须是 JSON object。")
    return parsed


def merge_deepseek_storyboard(
    storyboard: dict[str, Any],
    deepseek_result: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    merged = json.loads(json.dumps(storyboard, ensure_ascii=False))
    inferred_by_index = {
        int(shot.get("index")): shot
        for shot in deepseek_result.get("shots") or []
        if positive_int(shot.get("index"))
    }
    merged_shots = []
    for shot in merged.get("shots") or []:
        index = int(shot["index"])
        inferred = inferred_by_index.get(index) or {}
        if inferred:
            title = str(inferred.get("title") or shot.get("title") or "").strip()
            if title and not title.startswith(f"1-{index}"):
                title = f"1-{index} {title}"
            shot.update(
                {
                    "title": title or shot.get("title"),
                    "summary": str(inferred.get("summary") or shot.get("summary") or ""),
                    "characters": normalize_string_list(inferred.get("characters")),
                    "scene": normalize_string_list(inferred.get("scene")),
                    "props": normalize_string_list(inferred.get("props")),
                    "shotSize": normalize_choice(inferred.get("shotSize"), ["全景", "中景", "中近景", "近景", "特写"], "中景"),
                    "cameraAngle": normalize_choice(inferred.get("cameraAngle"), ["平视", "俯视", "仰视", "侧面"], "平视"),
                    "cameraMotion": normalize_choice(inferred.get("cameraMotion"), ["固定", "手持", "推镜", "拉镜", "跟拍"], "固定"),
                    "dialogues": normalize_dialogues(inferred.get("dialogues")),
                    "action": str(inferred.get("action") or ""),
                    "emotion": str(inferred.get("emotion") or ""),
                    "inferredPrompt": str(inferred.get("inferredPrompt") or inferred.get("prompt") or ""),
                    "reviewRequired": normalize_string_list(inferred.get("reviewRequired")),
                    "inferenceOnly": True,
                }
            )
        merged_shots.append(shot)
    merged["shots"] = merged_shots
    merged["deepseekInference"] = {
        "status": "completed",
        "model": model,
        "promptVersion": "text-storyboard-v1-zh-prompt",
        "inferredShots": len(inferred_by_index),
        "episodeContext": deepseek_result.get("episodeContext") or {},
    }
    return merged


def normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized = []
    for item in value:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def normalize_choice(value: object, allowed: list[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def normalize_dialogues(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    dialogues = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        speaker = str(item.get("speaker") or "").strip()
        if text:
            dialogues.append({"speaker": speaker, "text": text})
    return dialogues


def write_deepseek_log(
    log_path: Path,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    parsed: dict[str, Any],
) -> None:
    log_path.write_text(
        json.dumps(
            {
                "model": request_payload.get("model"),
                "request": request_payload,
                "response": response_payload,
                "parsedResult": parsed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def probe_video(ffmpeg_path: str, video_path: Path) -> dict[str, Any]:
    command = [
        ffprobe_path_for(ffmpeg_path),
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-show_streams",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        payload = json.loads(result.stdout or "{}")
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exception:
        raise SystemExit(f"读取视频信息失败：{video_path}\n{exception}") from exception
    video_stream = next((stream for stream in payload.get("streams") or [] if stream.get("codec_type") == "video"), {})
    return {
        "duration": positive_float((payload.get("format") or {}).get("duration")),
        "width": positive_int(video_stream.get("width")),
        "height": positive_int(video_stream.get("height")),
        "fps": parse_rate(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate")),
    }


def ffprobe_path_for(ffmpeg_path: str) -> str:
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name == "ffmpeg":
        return str(ffmpeg.with_name("ffprobe")) if ffmpeg.parent != Path(".") else "ffprobe"
    if ffmpeg.name.startswith("ffmpeg"):
        return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe", 1)))
    return "ffprobe"


def parse_rate(value: object) -> float | None:
    text = str(value or "")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            parsed_denominator = float(denominator)
            return float(numerator) / parsed_denominator if parsed_denominator else None
        except ValueError:
            return None
    return positive_float(text)


def positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def positive_float(value: object) -> float | None:
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def infer_title_and_episode(video_path: Path) -> tuple[str, str, int | None]:
    stem = video_path.stem
    match = re.search(r"(.+?)[-_ ]*第(\d+)集", stem)
    if match:
        title = match.group(1).strip("-_ ")
        episode_number = int(match.group(2))
        return title or stem, f"#{episode_number}集", episode_number
    return stem, "#1集", None


def aspect_ratio_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "9:16"
    ratio = width / height
    common_ratios = [("9:16", 9 / 16), ("16:9", 16 / 9), ("3:4", 3 / 4), ("4:3", 4 / 3), ("1:1", 1)]
    label, _ = min(common_ratios, key=lambda item: abs(ratio - item[1]))
    if abs(ratio - dict(common_ratios)[label]) < 0.05:
        return label
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def seconds_to_timecode(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


def prepare_output_paths(output_dir: Path) -> RenderPaths:
    keyframes_dir = output_dir / "keyframes"
    pages_dir = output_dir / "pages"
    screenshots_dir = output_dir / "分镜截图"
    for path in (keyframes_dir, pages_dir, screenshots_dir):
        path.mkdir(parents=True, exist_ok=True)
    return RenderPaths(output_dir, keyframes_dir, pages_dir, screenshots_dir)


def resolve_executable(value: str, executable_name: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if resolved:
        return resolved
    raise SystemExit(f"找不到 {executable_name} 可执行文件：{value}")


def resolve_chrome_path(value: str) -> str:
    candidate = Path(value).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    if resolved:
        return resolved
    raise SystemExit(f"找不到 Chrome 可执行文件：{value}")


def extract_keyframes(ffmpeg_path: str, video_path: Path, shots: list[dict[str, Any]], keyframes_dir: Path) -> None:
    for shot in shots:
        index = int(shot["index"])
        midpoint = (float(shot["start"]) + float(shot["end"])) / 2
        target = keyframes_dir / f"shot-{index:03d}.jpg"
        command = [
            ffmpeg_path,
            "-y",
            "-ss",
            f"{midpoint:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-update",
            "1",
            str(target),
        ]
        run_command(command, f"抽取关键帧失败：shot-{index:03d}")


def render_screenshots(
    chrome_path: str,
    storyboard: dict[str, Any],
    selected_shots: list[int],
    paths: RenderPaths,
    viewport: dict[str, float],
) -> list[Path]:
    shots = storyboard.get("shots") or []
    shots_by_index = {int(shot["index"]): shot for shot in shots}
    rendered: list[Path] = []
    with tempfile.TemporaryDirectory(prefix="aidrama-storyboard-chrome-") as profile_dir:
        for shot_index in selected_shots:
            shot = shots_by_index.get(shot_index)
            if not shot:
                raise SystemExit(f"storyboard 中找不到分镜：{shot_index}")
            page_path = paths.pages_dir / f"shot-{shot_index:03d}.html"
            page_path.write_text(render_html(storyboard, shot_index, paths.keyframes_dir), encoding="utf-8")
            screenshot_path = paths.screenshots_dir / f"分镜-{shot_index:03d}-完整工作台.png"
            command = [
                chrome_path,
                "--headless=new",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-default-apps",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
                "--run-all-compositor-stages-before-draw",
                f"--user-data-dir={profile_dir}",
                f"--window-size={int(viewport['width'])},{int(viewport['height'])}",
                f"--force-device-scale-factor={viewport['deviceScaleFactor']}",
                "--virtual-time-budget=1000",
                f"--screenshot={screenshot_path}",
                page_path.as_uri(),
            ]
            run_command(
                command,
                f"生成截图失败：shot-{shot_index:03d}",
                capture_output=False,
                success_path=screenshot_path,
                timeout_seconds=12,
            )
            rendered.append(screenshot_path)
    return rendered


def render_html(storyboard: dict[str, Any], selected_index: int, keyframes_dir: Path) -> str:
    shots = sorted(storyboard.get("shots") or [], key=lambda item: int(item["index"]))
    shots_by_index = {int(shot["index"]): shot for shot in shots}
    selected = shots_by_index[selected_index]
    workspace = storyboard.get("workspace") or {}
    drama = storyboard.get("drama") or {}
    episode = storyboard.get("episode") or {}
    duration = int(float(selected.get("duration") or selected.get("durationSeconds") or 15))
    scroll_top = 612 if selected_index >= 17 else 0

    def shot_image_uri(index: int) -> str:
        return (keyframes_dir / f"shot-{index:03d}.jpg").resolve().as_uri()

    previous_index = max(1, selected_index - 1)
    next_index = selected_index + 1 if selected_index + 1 in shots_by_index else selected_index
    reference_cards = [
        ("前一镜头", previous_index),
        ("当前镜头", selected_index),
        ("后一镜头", next_index),
    ]

    sidebar_items = "\n".join(
        render_sidebar_item(shot, shot_image_uri(int(shot["index"])), int(shot["index"]) == selected_index)
        for shot in shots
    )
    reference_items = "\n".join(
        render_reference_card(label, shot_image_uri(index)) for label, index in reference_cards
    )

    title = str(selected.get("title") or f"1-{selected_index}")
    summary = str(selected.get("summary") or selected.get("inferredPrompt") or "")
    summary_counter = f"{len(summary)}/{SUMMARY_MAX_CHARS}"
    characters = selected.get("characters") or []
    scenes = selected.get("scene") or []
    props = selected.get("props") or []
    shot_size = str(selected.get("shotSize") or "中景")
    camera_angle = str(selected.get("cameraAngle") or "平视")
    camera_motion = str(selected.get("cameraMotion") or "固定")
    selected_image = shot_image_uri(selected_index)
    model = str(selected.get("model") or workspace.get("models", ["Seedance 2.0"])[0])
    aspect_ratio = str(selected.get("aspectRatio") or "9:16")
    resolution = str(selected.get("resolution") or workspace.get("resolution") or "720 × 1280")
    fps = int(selected.get("fps") or workspace.get("fps") or 24)
    shot_subtitle = first_dialogue_text(selected)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; }}
    body {{
      color: #182033;
      background: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      font-size: 14px;
      letter-spacing: 0;
    }}
    .topbar {{
      height: 56px;
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 0 18px;
      border-bottom: 1px solid #e9edf5;
      white-space: nowrap;
    }}
    .back {{ font-size: 24px; color: #6a7282; }}
    .brand {{ display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 18px; margin-right: 8px; }}
    .logo {{ width: 24px; height: 24px; position: relative; }}
    .logo:before {{ content: ""; position: absolute; inset: 5px 4px; border-radius: 999px; background: linear-gradient(90deg, #5f7cff, #b700ff); }}
    .logo:after {{ content: ""; position: absolute; left: -3px; top: 9px; width: 12px; height: 5px; border-radius: 999px; background: #e7ddff; box-shadow: 18px 0 0 #824fff; }}
    .select-pill {{
      height: 36px;
      padding: 0 12px;
      border: 1px solid #dfe5ee;
      border-radius: 9px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: #40485a;
      background: #fff;
      font-size: 15px;
    }}
    .top-spacer {{ flex: 1; }}
    .balance {{ height: 40px; padding: 0 18px; border-radius: 999px; background: #fafbff; border: 1px solid #eceff6; display: flex; align-items: center; gap: 8px; font-size: 15px; }}
    .balance strong {{ color: #ff4b91; }}
    .username {{ font-weight: 800; font-size: 16px; }}
    .main {{ display: flex; height: calc(100vh - 56px); min-height: 0; }}
    .sidebar {{ width: 200px; border-right: 1px solid #e8edf5; display: flex; flex-direction: column; min-height: 0; }}
    .sidebar-head {{ height: 40px; padding: 0 12px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e8edf5; font-weight: 800; }}
    .sidebar-head span:last-child {{ color: #748095; font-weight: 500; }}
    .shot-list {{ flex: 1; min-height: 0; overflow-y: auto; padding: 8px 8px 10px; }}
    .shot-item {{ height: 64px; display: flex; gap: 10px; align-items: center; padding: 6px; border-radius: 8px; border: 1px solid transparent; margin-bottom: 4px; }}
    .shot-item.active {{ border-color: #9638ff; background: #fbf7ff; }}
    .thumb {{ width: 64px; height: 45px; border-radius: 5px; object-fit: cover; background: #111; flex: 0 0 auto; }}
    .shot-copy {{ min-width: 0; flex: 1; }}
    .shot-title {{ font-weight: 800; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .shot-meta {{ margin-top: 5px; color: #697386; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .sidebar-actions {{ height: 38px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 5px 8px; border-top: 1px solid #e8edf5; }}
    .mini-button {{ border: 1px solid #dce2ec; border-radius: 8px; background: #fff; color: #31394a; font-weight: 600; }}
    .editor {{ width: 480px; border-right: 1px solid #e8edf5; display: flex; flex-direction: column; min-height: 0; }}
    .editor-head {{ height: 40px; padding: 0 16px; border-bottom: 1px solid #e8edf5; display: flex; align-items: center; justify-content: space-between; }}
    .editor-title {{ font-weight: 800; font-size: 15px; }}
    .counter {{ color: #8b95a7; }}
    .editor-body {{ flex: 1; overflow: hidden; padding: 14px 16px; }}
    .section-title {{ font-weight: 800; margin: 0 0 8px; font-size: 15px; }}
    .summary-box {{ width: 100%; height: 114px; border: 1px solid #dfe5ee; border-radius: 8px; padding: 12px; line-height: 1.55; color: #243047; resize: none; font: inherit; overflow: hidden; }}
    .element-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 8px; }}
    .metric {{ height: 34px; border: 1px solid #cda7ff; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; font-size: 15px; }}
    .metric strong {{ font-size: 16px; }}
    .select-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 10px; }}
    .field {{ height: 32px; border: 1px solid #dfe5ee; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; padding: 0 10px; color: #606b7f; background: #fff; }}
    .field strong {{ color: #343c4d; font-weight: 600; }}
    .tabs {{ display: grid; grid-template-columns: repeat(4, 1fr); height: 36px; border: 1px solid #dfe5ee; border-radius: 9px; overflow: hidden; margin-bottom: 8px; }}
    .tab {{ display: flex; align-items: center; justify-content: center; color: #1f2937; }}
    .tab.active {{ color: #fff; background: linear-gradient(90deg, #7a35ff, #982cff); font-weight: 800; border-radius: 8px; margin: 2px; }}
    .references {{ height: 98px; border: 1px solid #dfe5ee; border-radius: 9px; display: flex; align-items: center; gap: 9px; padding: 9px; margin-bottom: 8px; }}
    .add-card {{ width: 82px; height: 80px; border: 1px dashed #d7dde8; border-radius: 7px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; color: #586276; }}
    .add-card b {{ font-size: 22px; line-height: 1; }}
    .ref-card {{ width: 80px; height: 80px; border-radius: 6px; overflow: hidden; position: relative; background: #111; flex: 0 0 auto; }}
    .ref-card img {{ width: 100%; height: 100%; object-fit: cover; }}
    .ref-card span {{ position: absolute; left: 0; right: 0; bottom: 0; padding: 4px 6px; color: #fff; font-size: 12px; background: linear-gradient(transparent, rgba(0,0,0,.72)); }}
    .prompt-box {{ height: 104px; border: 1px solid #dfe5ee; border-radius: 9px; color: #9aa3b3; padding: 14px 12px; margin-bottom: 8px; font-size: 15px; }}
    .model-row {{ display: grid; grid-template-columns: 1fr 152px; gap: 10px; margin-bottom: 8px; }}
    .model-select {{ height: 34px; border: 1px solid #bf8fff; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; padding: 0 12px; }}
    .prompt-button {{ height: 34px; border: 0; border-radius: 8px; color: #fff; font-weight: 800; background: linear-gradient(90deg, #4f7cff, #b700ff); }}
    .notice {{ height: 34px; display: flex; align-items: center; padding: 0 10px; border-radius: 8px; background: #fff1cf; color: #bc751d; margin-bottom: 8px; }}
    .generation-options {{ height: 34px; border: 1px solid #dfe5ee; border-radius: 8px; display: grid; grid-template-columns: repeat(4, 1fr); align-items: center; text-align: center; color: #4b5567; overflow: hidden; margin-bottom: 8px; }}
    .generation-options div + div {{ border-left: 1px solid #e1e6ef; }}
    .start-button {{ width: 100%; height: 40px; border: 0; border-radius: 8px; color: #fff; font-weight: 900; font-size: 16px; background: linear-gradient(90deg, #4f7cff, #b700ff); }}
    .preview {{ flex: 1; min-width: 0; border-right: 1px solid #e8edf5; display: flex; flex-direction: column; }}
    .stage {{ height: 404px; padding: 54px 16px 0; border-bottom: 1px solid #e8edf5; }}
    .tool-row {{ display: flex; justify-content: flex-end; gap: 8px; margin-bottom: 14px; }}
    .tool {{ width: 32px; height: 32px; border-radius: 7px; background: #777; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 800; }}
    .player {{ height: 277px; width: 100%; border-radius: 7px; background: #0d0d0f; overflow: hidden; position: relative; display: flex; align-items: center; justify-content: center; }}
    .player img {{ height: 100%; width: auto; display: block; }}
    .big-play {{ position: absolute; width: 52px; height: 52px; border-radius: 999px; background: rgba(255,255,255,.72); display: flex; align-items: center; justify-content: center; color: #7b27ff; font-size: 28px; padding-left: 4px; }}
    .time {{ position: absolute; left: 42px; bottom: 12px; color: #fff; font-weight: 700; font-size: 15px; }}
    .tiny-play {{ position: absolute; left: 18px; bottom: 13px; color: #fff; font-size: 15px; }}
    .burned-subtitle {{ position: absolute; bottom: 68px; color: white; text-shadow: 0 1px 3px rgba(0,0,0,.7); font-weight: 700; font-size: 12px; max-width: 170px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .library {{ flex: 1; min-height: 0; padding: 12px 16px; }}
    .library-tabs {{ display: flex; align-items: center; gap: 22px; height: 34px; margin-bottom: 18px; }}
    .library-tabs strong {{ font-weight: 900; }}
    .library-tabs .active {{ background: #8737ff; color: #fff; border-radius: 8px; padding: 6px 10px; font-weight: 800; }}
    .asset-thumb {{ width: 118px; height: 67px; border: 2px solid #9638ff; border-radius: 8px; overflow: hidden; position: relative; background: #111; }}
    .asset-thumb img {{ width: 100%; height: 100%; object-fit: cover; }}
    .asset-thumb .small-play {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 30px; height: 30px; border-radius: 50%; background: white; color: #7b27ff; display: flex; align-items: center; justify-content: center; padding-left: 2px; }}
    .pager {{ position: absolute; right: 36px; bottom: 18px; display: flex; align-items: center; gap: 12px; color: #7a8496; }}
    .page-size {{ border: 1px solid #dce2ec; border-radius: 8px; padding: 8px 14px; color: #495467; background: #fff; }}
    .side-panel {{ width: 265px; padding: 20px 12px; position: relative; }}
    .close {{ position: absolute; right: 16px; top: 18px; font-size: 22px; }}
    .config-card {{ border: 1px solid #dfe5ee; border-radius: 10px; min-height: 106px; padding: 12px; margin-top: 34px; margin-bottom: 12px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{ color: #944fff; background: #f1ddff; border-radius: 999px; padding: 6px 10px; font-weight: 700; }}
    .action-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .side-action {{ height: 40px; border: 1px solid #caa4ff; border-radius: 7px; color: #9344ff; background: #fff; font-weight: 800; }}
    .edit-button {{ height: 42px; margin-top: 8px; width: 100%; border: 0; border-radius: 8px; color: #fff; background: linear-gradient(90deg, #2f68ff, #b400ff); font-size: 16px; font-weight: 900; }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="back">‹</div>
    <div class="brand"><span class="logo"></span><span>绘梦工坊</span></div>
    <div class="select-pill">剧本： <strong>{escape(str(workspace.get("scriptName") or drama.get("title") or ""))}</strong>⌄</div>
    <div class="select-pill">剧集： <strong>{escape(str(workspace.get("episodeLabel") or episode.get("title") or ""))}</strong>⌄</div>
    <div class="select-pill">风格： <strong>{escape(str(workspace.get("style") or DEFAULT_STYLE))}</strong>⌄</div>
    <div class="top-spacer"></div>
    <div class="balance">积分余额：<strong>{escape(str(workspace.get("pointsBalance") or "9783.738"))}</strong></div>
    <div class="username">{escape(str(workspace.get("username") or DEFAULT_MEDIA_ACCOUNT_NAME))}</div>
  </div>
  <div class="main">
    <aside class="sidebar">
      <div class="sidebar-head"><span>分镜表</span><span>{len(shots)} 个镜头</span></div>
      <div class="shot-list" id="shot-list" data-scroll-top="{scroll_top}">{sidebar_items}</div>
      <div class="sidebar-actions"><button class="mini-button">+ 新建分镜</button><button class="mini-button">导出</button></div>
    </aside>
    <section class="editor">
      <div class="editor-head"><div class="editor-title">{escape(title)}</div><div class="counter">{escape(summary_counter)}</div></div>
      <div class="editor-body">
        <div class="section-title">分镜概要</div>
        <textarea class="summary-box">{escape(summary)}</textarea>
        <div class="section-title">画面要素</div>
        <div class="element-grid">
          <div class="metric">角色 <strong>{len(characters)}</strong></div>
          <div class="metric">场景 <strong>{len(scenes)}</strong></div>
          <div class="metric">道具 <strong>{len(props)}</strong></div>
        </div>
        <div class="select-row">
          <div class="field">景别 <strong>{escape(shot_size)}</strong>⌄</div>
          <div class="field">角度 <strong>{escape(camera_angle)}</strong>⌄</div>
          <div class="field">运镜 <strong>{escape(camera_motion)}</strong>⌄</div>
        </div>
        <div class="section-title">对话内容</div>
        <div class="tabs"><div class="tab">文生图</div><div class="tab">图生图</div><div class="tab active">参考生视频</div><div class="tab">图生视频</div></div>
        <div class="references"><div class="add-card"><b>＋</b><span>点击添加</span></div>{reference_items}</div>
        <div class="prompt-box">先选择参考图片，然后描述您想生成的视频效果...</div>
        <div class="model-row">
          <div class="model-select">{escape(model)} <span>⌄</span></div>
          <button class="prompt-button">生成提示词 ✧ {escape(str(workspace.get("promptPoints") or "0.056"))}</button>
        </div>
        <div class="notice">ⓘ 模型说明：多主体参考、真人效果好</div>
        <div class="generation-options"><div>720p</div><div>{escape(aspect_ratio)}</div><div>{duration}s</div><div>1条</div></div>
        <button class="start-button">开始生成 ✧ {escape(str(workspace.get("generationPoints") or "151"))}</button>
      </div>
    </section>
    <section class="preview">
      <div class="stage">
        <div class="tool-row"><div class="tool">□</div><div class="tool">⇧</div><div class="tool">⇩</div><div class="tool">☆</div><div class="tool">ⓘ</div><div class="tool">⋮</div></div>
        <div class="player">
          <img src="{selected_image}" alt="">
          <div class="big-play">▶</div>
          <div class="tiny-play">▶</div>
          <div class="time">0:00 / 0:{duration:02d}</div>
          <div class="burned-subtitle">{escape(shot_subtitle)}</div>
        </div>
      </div>
      <div class="library">
        <div class="library-tabs"><strong>▦ 素材库</strong><span class="active">当前分镜</span><span>所有分镜</span><span>全部</span><span>图片</span><span>视频</span><span>音频</span></div>
        <div class="asset-thumb"><img src="{selected_image}" alt=""><div class="small-play">▶</div></div>
        <div class="pager"><span>共 1 条</span><div class="page-size">24条/页⌄</div></div>
      </div>
    </section>
    <aside class="side-panel">
      <div class="close">×</div>
      <div class="config-card">
        <div class="chips">
          <span class="chip">{escape(model)}</span><span class="chip">{escape(aspect_ratio)}</span><span class="chip">{duration}s</span>
          <span class="chip">{escape(resolution)}</span><span class="chip">{fps}FPS</span>
        </div>
      </div>
      <div class="action-grid">
        <button class="side-action">视频修改</button><button class="side-action">视频延长</button>
        <button class="side-action">对口型-仅单人</button><button class="side-action">对口型-单人/多人</button>
        <button class="side-action">超分</button><button class="side-action">插帧</button>
        <button class="side-action">抽帧</button><button class="side-action">字幕擦除</button>
      </div>
      <button class="edit-button">↻　重新编辑</button>
    </aside>
  </div>
  <script>
    const list = document.getElementById("shot-list");
    list.scrollTop = Number(list.dataset.scrollTop || "0");
  </script>
</body>
</html>"""


def render_sidebar_item(shot: dict[str, Any], image_uri: str, active: bool) -> str:
    title = str(shot.get("title") or f"1-{shot.get('index')}")
    summary = str(shot.get("summary") or "")
    active_class = " active" if active else ""
    return (
        f'<div class="shot-item{active_class}">'
        f'<img class="thumb" src="{image_uri}" alt="">'
        '<div class="shot-copy">'
        f'<div class="shot-title">{escape(title)}</div>'
        f'<div class="shot-meta">{escape(summary)}</div>'
        "</div></div>"
    )


def render_reference_card(label: str, image_uri: str) -> str:
    return f'<div class="ref-card"><img src="{image_uri}" alt=""><span>{escape(label)}</span></div>'


def first_dialogue_text(shot: dict[str, Any]) -> str:
    dialogues = shot.get("dialogues") or []
    for dialogue in dialogues:
        text = str((dialogue or {}).get("text") or "").strip()
        if text:
            return text[:18]
    return ""


def run_command(
    command: list[str],
    failure_message: str,
    *,
    capture_output: bool = True,
    success_path: Path | None = None,
    timeout_seconds: float | None = None,
) -> None:
    try:
        if capture_output:
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout_seconds)
        else:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_seconds,
            )
    except subprocess.CalledProcessError as exception:
        if path_has_content(success_path):
            return
        detail = process_output_tail(exception.stdout, exception.stderr)
        raise SystemExit(f"{failure_message}\n{detail}") from exception
    except subprocess.TimeoutExpired as exception:
        if path_has_content(success_path):
            return
        raise SystemExit(f"{failure_message}\n命令超时：{exception}") from exception
    except OSError as exception:
        raise SystemExit(f"{failure_message}\n{exception}") from exception


def path_has_content(path: Path | None) -> bool:
    if not path:
        return False
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False


def process_output_tail(stdout: str | None, stderr: str | None, max_lines: int = 10, max_chars: int = 1600) -> str:
    text = "\n".join(part for part in (stderr, stdout) if part)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "没有返回错误详情"
    return "\n".join(lines[-max_lines:])[-max_chars:]


if __name__ == "__main__":
    main()
