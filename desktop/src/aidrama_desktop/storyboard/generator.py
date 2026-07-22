from __future__ import annotations

import json
import math
import random
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Iterator

import httpx


DEFAULT_VIEWPORT_WIDTH = 1470
DEFAULT_VIEWPORT_HEIGHT = 835
DEFAULT_DEVICE_SCALE_FACTOR = 2
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_API_BASE = "https://api.deepseek.com"
DEFAULT_STYLE = "真人风格-国产都市"
DEFAULT_MEDIA_ACCOUNT_NAME = "用户1182"
COSTUME_STYLE = "真人风格-古代"
DEFAULT_TARGET_SHOTS = 15
DEFAULT_RANDOM_TARGET_SHOTS_MIN = 15
DEFAULT_RANDOM_TARGET_SHOTS_MAX = 20
DEFAULT_SCREENSHOT_COUNT = 3
SUMMARY_MIN_CHARS = 150
SUMMARY_MAX_CHARS = 300
DEEPSEEK_TIMEOUT_SECONDS = 120
CHROME_SCREENSHOT_TIMEOUT_SECONDS = 12
COSTUME_CATEGORY_IDS = {"costume"}
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


class StoryboardGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoryboardGenerationConfig:
    enabled: bool = False
    deepseek_api_base: str = DEFAULT_API_BASE
    deepseek_api_key: str = ""
    deepseek_model: str = DEFAULT_MODEL
    target_shots: int | None = None
    style: str = DEFAULT_STYLE

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "StoryboardGenerationConfig":
        data = payload or {}
        target_shots = positive_int(data.get("targetShots"))
        return cls(
            enabled=bool(data.get("enabled")),
            deepseek_api_base=str(data.get("deepseekApiBase") or DEFAULT_API_BASE),
            deepseek_api_key=str(data.get("deepseekApiKey") or ""),
            deepseek_model=str(data.get("deepseekModel") or DEFAULT_MODEL),
            target_shots=None if target_shots == DEFAULT_TARGET_SHOTS else target_shots,
            style=str(data.get("style") or DEFAULT_STYLE),
        )


@dataclass
class StoryboardGenerator:
    ffmpeg_path: str = "ffmpeg"
    chrome_path: str | None = None

    def generate(
        self,
        *,
        source_video: Path,
        drama_title: str,
        episode_label: str,
        media_account: str,
        output_dir: Path,
        config: StoryboardGenerationConfig,
    ) -> list[Path]:
        if not config.enabled:
            return []
        if not config.deepseek_api_key.strip():
            raise StoryboardGenerationError("系统配置 storyboard.deepseekApiKey 为空，无法生成分镜图。")
        if not source_video.exists():
            raise StoryboardGenerationError(f"分镜视频不存在：{source_video}")

        output_dir.mkdir(parents=True, exist_ok=True)
        keyframes_dir = output_dir / "keyframes"
        pages_dir = output_dir / "pages"
        screenshots_dir = output_dir / "分镜截图"
        keyframes_dir.mkdir(parents=True, exist_ok=True)
        pages_dir.mkdir(parents=True, exist_ok=True)
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        storyboard = self._build_storyboard(
            source_video=source_video,
            drama_title=drama_title,
            episode_label=episode_label,
            media_account=media_account,
            config=config,
        )
        self._extract_keyframes(source_video, storyboard["shots"], keyframes_dir)
        storyboard = self._enrich_with_deepseek(storyboard, config)
        (output_dir / "storyboard.generated.json").write_text(
            json.dumps(storyboard, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return self._render_screenshots(storyboard, keyframes_dir, pages_dir, screenshots_dir)

    def _build_storyboard(
        self,
        *,
        source_video: Path,
        drama_title: str,
        episode_label: str,
        media_account: str,
        config: StoryboardGenerationConfig,
    ) -> dict[str, Any]:
        probe = self._probe_video(source_video)
        duration = float(probe.get("duration") or 0)
        if duration <= 0:
            raise StoryboardGenerationError(f"无法读取视频时长：{source_video}")
        width = int(probe.get("width") or 720)
        height = int(probe.get("height") or 1280)
        fps = float(probe.get("fps") or 30)
        total = resolve_target_shot_count(config.target_shots)
        segment_seconds = duration / total
        balance = f"{random.uniform(2000, 18000):.3f}"
        style = infer_storyboard_style(title=drama_title, configured_style=config.style)
        shots: list[dict[str, Any]] = []
        for offset in range(total):
            start = round(offset * segment_seconds, 3)
            end = round(duration if offset == total - 1 else (offset + 1) * segment_seconds, 3)
            index = offset + 1
            shot_duration = max(0.1, round(end - start, 3))
            shots.append(
                {
                    "id": f"storyboard-shot-{index:03d}",
                    "index": index,
                    "title": f"1-{index} 自动分镜",
                    "start": start,
                    "end": end,
                    "startTimecode": seconds_to_timecode(start),
                    "endTimecode": seconds_to_timecode(end),
                    "durationSeconds": shot_duration,
                    "summary": "根据视频自动切分生成，剧情摘要由 DeepSeek 补全。",
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
                    "aspectRatio": aspect_ratio_label(width, height),
                    "duration": max(1, int(round(shot_duration))),
                    "resolution": f"{width} × {height}",
                    "fps": int(round(fps)),
                    "assets": [{"type": "keyframe", "path": f"keyframes/shot-{index:03d}.jpg"}],
                    "keyframe": f"keyframes/shot-{index:03d}.jpg",
                    "sourceStart": start,
                    "sourceEnd": end,
                    "sourceStartTimecode": seconds_to_timecode(start),
                    "sourceEndTimecode": seconds_to_timecode(end),
                }
            )
        return {
            "version": 1,
            "drama": {"title": drama_title, "sourceTitle": drama_title},
            "episode": {"title": episode_label},
            "source": {
                "video": str(source_video),
                "duration": duration,
                "width": width,
                "height": height,
                "fps": fps,
            },
            "totalShots": len(shots),
            "workspace": {
                "scriptName": drama_title,
                "episodeLabel": episode_label,
                "style": style,
                "username": media_account or DEFAULT_MEDIA_ACCOUNT_NAME,
                "pointsBalance": balance,
                "promptPoints": 0.056,
                "generationPoints": 151,
                "resolution": f"{width} × {height}",
                "fps": int(round(fps)),
            },
            "deepseekInference": {"status": "not-started", "inferredShots": 0},
            "shots": shots,
        }

    def _probe_video(self, source_video: Path) -> dict[str, Any]:
        command = [
            ffprobe_path_for(self.ffmpeg_path),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_streams",
            "-of",
            "json",
            str(source_video),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exception:
            raise StoryboardGenerationError(f"读取视频信息失败：{exception}") from exception
        stream = next((item for item in payload.get("streams") or [] if item.get("codec_type") == "video"), {})
        return {
            "duration": positive_float((payload.get("format") or {}).get("duration")),
            "width": positive_int(stream.get("width")),
            "height": positive_int(stream.get("height")),
            "fps": parse_rate(stream.get("avg_frame_rate") or stream.get("r_frame_rate")),
        }

    def _extract_keyframes(self, source_video: Path, shots: list[dict[str, Any]], keyframes_dir: Path) -> None:
        for shot in shots:
            index = int(shot["index"])
            midpoint = (float(shot["start"]) + float(shot["end"])) / 2
            target = keyframes_dir / f"shot-{index:03d}.jpg"
            command = [
                self.ffmpeg_path,
                "-y",
                "-ss",
                f"{midpoint:.3f}",
                "-i",
                str(source_video),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-update",
                "1",
                str(target),
            ]
            run_command(command, f"抽取分镜关键帧失败：shot-{index:03d}")

    def _enrich_with_deepseek(
        self,
        storyboard: dict[str, Any],
        config: StoryboardGenerationConfig,
    ) -> dict[str, Any]:
        request_payload = build_deepseek_request(storyboard, config.deepseek_model)
        url = config.deepseek_api_base.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.deepseek_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
                response = client.post(url, json=request_payload, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exception:
            detail = exception.response.text[-800:] if exception.response is not None else ""
            raise StoryboardGenerationError(f"DeepSeek 分镜分析失败：HTTP {exception.response.status_code} {detail}") from exception
        except (httpx.RequestError, ValueError) as exception:
            raise StoryboardGenerationError(f"DeepSeek 分镜分析失败：{exception}") from exception
        content = deepseek_content(payload)
        parsed = parse_json_object(content)
        return merge_deepseek_storyboard(storyboard, parsed, config.deepseek_model)

    def _render_screenshots(
        self,
        storyboard: dict[str, Any],
        keyframes_dir: Path,
        pages_dir: Path,
        screenshots_dir: Path,
    ) -> list[Path]:
        chrome = resolve_chrome_path(self.chrome_path)
        shots = storyboard.get("shots") or []
        selected_indexes = sample_shot_indexes(len(shots), DEFAULT_SCREENSHOT_COUNT)
        selected = {index for index in selected_indexes}
        rendered: list[Path] = []
        with temporary_chrome_profile_dir() as profile_dir:
            for shot in shots:
                index = int(shot["index"])
                if index not in selected:
                    continue
                page = pages_dir / f"shot-{index:03d}.html"
                page.write_text(render_html(storyboard, index, keyframes_dir), encoding="utf-8")
                screenshot = screenshots_dir / f"分镜-{index:03d}-完整工作台.png"
                command = [
                    chrome,
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
                    f"--window-size={DEFAULT_VIEWPORT_WIDTH},{DEFAULT_VIEWPORT_HEIGHT}",
                    f"--force-device-scale-factor={DEFAULT_DEVICE_SCALE_FACTOR}",
                    "--virtual-time-budget=1000",
                    f"--screenshot={screenshot}",
                    page.as_uri(),
                ]
                run_command(
                    command,
                    f"生成分镜工程图失败：shot-{index:03d}",
                    capture_output=False,
                    success_path=screenshot,
                    timeout_seconds=CHROME_SCREENSHOT_TIMEOUT_SECONDS,
                )
                rendered.append(screenshot)
        return rendered


@contextmanager
def temporary_chrome_profile_dir() -> Iterator[str]:
    profile_dir = tempfile.mkdtemp(prefix="aidrama-storyboard-chrome-")
    try:
        yield profile_dir
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)


def resolve_target_shot_count(target_shots: int | None) -> int:
    if target_shots:
        return max(int(target_shots), 1)
    return random.randint(DEFAULT_RANDOM_TARGET_SHOTS_MIN, DEFAULT_RANDOM_TARGET_SHOTS_MAX)


def sample_shot_indexes(total_shots: int, count: int) -> list[int]:
    if total_shots <= 0 or count <= 0:
        return []
    sample_size = min(total_shots, count)
    return sorted(random.sample(range(1, total_shots + 1), sample_size))


def infer_storyboard_style(
    *,
    title: str = "",
    summary: str = "",
    category_ids: Iterable[object] | str | None = None,
    configured_style: str = "",
) -> str:
    configured = str(configured_style or "").strip()
    if configured and configured != DEFAULT_STYLE:
        return configured
    normalized_category_ids = normalize_category_ids(category_ids)
    if normalized_category_ids & COSTUME_CATEGORY_IDS:
        return COSTUME_STYLE
    text = f"{title or ''} {summary or ''}".lower()
    if any(keyword.lower() in text for keyword in COSTUME_STYLE_KEYWORDS):
        return COSTUME_STYLE
    return configured or DEFAULT_STYLE


def normalize_category_ids(category_ids: Iterable[object] | str | None) -> set[str]:
    if not category_ids:
        return set()
    if isinstance(category_ids, str):
        values: Iterable[object] = re.split(r"[,，\s]+", category_ids)
    else:
        values = category_ids
    return {str(value).strip().lower() for value in values if str(value).strip()}


def build_deepseek_request(storyboard: dict[str, Any], model: str) -> dict[str, Any]:
    drama = storyboard.get("drama") or {}
    episode = storyboard.get("episode") or {}
    source = storyboard.get("source") or {}
    workspace = storyboard.get("workspace") or {}
    shots = [
        {
            "index": shot.get("index"),
            "startTimecode": shot.get("startTimecode"),
            "endTimecode": shot.get("endTimecode"),
            "durationSeconds": shot.get("durationSeconds"),
        }
        for shot in storyboard.get("shots") or []
    ]
    user_payload = {
        "task": "补全短剧分镜工程图字段",
        "constraints": [
            "只输出 JSON object，不要 Markdown。",
            "shots 数量必须与输入一致，index 必须一一对应。",
            "没有字幕和视觉识别时，不要编造具体对白。",
            f"title 控制 4-8 个中文字符，summary 控制 {SUMMARY_MIN_CHARS}-{SUMMARY_MAX_CHARS} 个中文字符，"
            "至少达到原合格长度的 5 倍；重点补足人物状态、动作推进、环境氛围、镜头关系和剧情张力。",
            "shotSize 只能选：全景、中景、中近景、近景、特写。",
            "cameraAngle 只能选：平视、俯视、仰视、侧面。",
            "cameraMotion 只能选：固定、手持、推镜、拉镜、跟拍。",
        ],
        "input": {
            "dramaTitle": drama.get("title"),
            "episodeLabel": episode.get("title"),
            "style": workspace.get("style"),
            "source": {
                "duration": source.get("duration"),
                "width": source.get("width"),
                "height": source.get("height"),
                "fps": source.get("fps"),
            },
            "shots": shots,
        },
        "outputSchema": {
            "shots": [
                {
                    "index": 1,
                    "title": "分镜标题",
                    "summary": "150-300字分镜概要",
                    "characters": ["人物"],
                    "scene": ["场景"],
                    "props": ["道具"],
                    "shotSize": "中景",
                    "cameraAngle": "平视",
                    "cameraMotion": "固定",
                    "action": "动作描述",
                    "emotion": "情绪",
                    "dialogues": [{"speaker": "", "text": ""}],
                    "inferredPrompt": "视频生成提示词",
                    "reviewRequired": ["需要人工确认的问题"],
                }
            ]
        },
    }
    return {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是短剧分镜导演和 AIGC 视频提示词策划。"
                    "根据剧名、剧集、视频时长和分镜时间轴，生成适合分镜工作台展示的中文 JSON。"
                ),
            },
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
        ],
    }


def deepseek_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        raise StoryboardGenerationError("DeepSeek 响应缺少 choices。")
    content = (choices[0].get("message") or {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise StoryboardGenerationError("DeepSeek 响应缺少 message.content。")
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
        raise StoryboardGenerationError("DeepSeek 输出必须是 JSON object。")
    return parsed


def merge_deepseek_storyboard(
    storyboard: dict[str, Any],
    result: dict[str, Any],
    model: str,
) -> dict[str, Any]:
    merged = json.loads(json.dumps(storyboard, ensure_ascii=False))
    by_index = {
        int(item.get("index")): item
        for item in result.get("shots") or []
        if positive_int(item.get("index"))
    }
    for shot in merged.get("shots") or []:
        index = int(shot["index"])
        item = by_index.get(index) or {}
        if not item:
            continue
        title = str(item.get("title") or shot.get("title") or "").strip()
        if title and not title.startswith(f"1-{index}"):
            title = f"1-{index} {title}"
        shot.update(
            {
                "title": title or shot.get("title"),
                "summary": str(item.get("summary") or shot.get("summary") or ""),
                "characters": normalize_string_list(item.get("characters")),
                "scene": normalize_string_list(item.get("scene")),
                "props": normalize_string_list(item.get("props")),
                "shotSize": normalize_choice(item.get("shotSize"), ["全景", "中景", "中近景", "近景", "特写"], "中景"),
                "cameraAngle": normalize_choice(item.get("cameraAngle"), ["平视", "俯视", "仰视", "侧面"], "平视"),
                "cameraMotion": normalize_choice(item.get("cameraMotion"), ["固定", "手持", "推镜", "拉镜", "跟拍"], "固定"),
                "dialogues": normalize_dialogues(item.get("dialogues")),
                "action": str(item.get("action") or ""),
                "emotion": str(item.get("emotion") or ""),
                "inferredPrompt": str(item.get("inferredPrompt") or item.get("prompt") or ""),
                "reviewRequired": normalize_string_list(item.get("reviewRequired")),
                "inferenceOnly": True,
            }
        )
    merged["deepseekInference"] = {
        "status": "completed",
        "model": model,
        "promptVersion": "text-storyboard-v1-zh-prompt",
        "inferredShots": len(by_index),
    }
    return merged


def render_html(storyboard: dict[str, Any], selected_index: int, keyframes_dir: Path) -> str:
    shots = sorted(storyboard.get("shots") or [], key=lambda item: int(item["index"]))
    selected = next(item for item in shots if int(item["index"]) == selected_index)
    workspace = storyboard.get("workspace") or {}
    image_uri = (keyframes_dir / f"shot-{selected_index:03d}.jpg").resolve().as_uri()
    sidebar = "\n".join(render_sidebar_item(shot, keyframes_dir, selected_index) for shot in shots)
    refs = "\n".join(
        render_ref_card(label, keyframes_dir / f"shot-{index:03d}.jpg")
        for label, index in reference_indexes(selected_index, len(shots))
    )
    title = str(selected.get("title") or f"1-{selected_index} 自动分镜")
    summary = str(selected.get("summary") or "")
    summary_counter = f"{len(summary)}/{SUMMARY_MAX_CHARS}"
    duration = int(selected.get("duration") or max(1, round(float(selected.get("durationSeconds") or 15))))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;overflow:hidden}}body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#172033;background:white;font-size:14px}}.top{{height:56px;display:flex;align-items:center;gap:12px;padding:0 18px;border-bottom:1px solid #e9edf5}}.brand{{font-size:18px;font-weight:800}}.pill{{height:36px;border:1px solid #dfe5ee;border-radius:9px;padding:0 12px;display:flex;align-items:center;gap:8px}}.spacer{{flex:1}}.balance{{height:40px;border:1px solid #eceff6;border-radius:999px;padding:0 18px;display:flex;align-items:center;gap:8px;background:#fafbff}}.balance b{{color:#ff4b91}}.user{{font-weight:800;font-size:16px}}.main{{display:flex;height:calc(100vh - 56px)}}.side{{width:200px;border-right:1px solid #e8edf5;display:flex;flex-direction:column}}.side-head{{height:40px;padding:0 12px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #e8edf5;font-weight:800}}.list{{flex:1;overflow-y:auto;padding:8px}}.shot{{height:64px;display:flex;gap:10px;align-items:center;padding:6px;border-radius:8px;border:1px solid transparent;margin-bottom:4px}}.shot.active{{border-color:#9638ff;background:#fbf7ff}}.thumb{{width:64px;height:45px;border-radius:5px;object-fit:cover;background:#111}}.shot-title{{font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.shot-meta{{margin-top:5px;color:#697386;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.editor{{width:480px;border-right:1px solid #e8edf5;display:flex;flex-direction:column}}.editor-head{{height:40px;padding:0 16px;border-bottom:1px solid #e8edf5;display:flex;align-items:center;justify-content:space-between;font-weight:800}}.editor-body{{padding:14px 16px}}.section{{font-weight:800;margin:0 0 8px;font-size:15px}}.summary{{height:114px;border:1px solid #dfe5ee;border-radius:8px;padding:12px;line-height:1.55;margin-bottom:12px;overflow:hidden}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}}.metric,.field{{height:34px;border:1px solid #cda7ff;border-radius:8px;display:flex;align-items:center;justify-content:space-between;padding:0 12px}}.field{{border-color:#dfe5ee;color:#606b7f}}.tabs{{display:grid;grid-template-columns:repeat(4,1fr);height:36px;border:1px solid #dfe5ee;border-radius:9px;overflow:hidden;margin-bottom:8px}}.tab{{display:flex;align-items:center;justify-content:center}}.tab.active{{color:white;background:#8737ff;border-radius:8px;margin:2px;font-weight:800}}.refs{{height:98px;border:1px solid #dfe5ee;border-radius:9px;display:flex;gap:9px;align-items:center;padding:9px;margin-bottom:8px}}.add{{width:82px;height:80px;border:1px dashed #d7dde8;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-direction:column;color:#586276}}.ref{{width:80px;height:80px;border-radius:6px;overflow:hidden;position:relative;background:#111}}.ref img{{width:100%;height:100%;object-fit:cover}}.ref span{{position:absolute;left:0;right:0;bottom:0;color:white;font-size:12px;padding:4px 6px;background:linear-gradient(transparent,rgba(0,0,0,.72))}}.prompt{{height:104px;border:1px solid #dfe5ee;border-radius:9px;color:#9aa3b3;padding:14px 12px;margin-bottom:8px}}.btn{{height:40px;border:0;border-radius:8px;color:white;background:linear-gradient(90deg,#4f7cff,#b700ff);font-weight:900;font-size:16px;width:100%}}.preview{{flex:1;border-right:1px solid #e8edf5}}.stage{{height:404px;padding:92px 16px 0;border-bottom:1px solid #e8edf5}}.player{{height:277px;width:100%;border-radius:7px;background:#0d0d0f;overflow:hidden;position:relative;display:flex;align-items:center;justify-content:center}}.player img{{max-width:100%;max-height:100%;width:auto;height:auto}}.play{{position:absolute;width:52px;height:52px;border-radius:999px;background:rgba(255,255,255,.72);display:flex;align-items:center;justify-content:center;color:#7b27ff;font-size:28px;padding-left:4px}}.time{{position:absolute;left:42px;bottom:12px;color:#fff;font-weight:700;font-size:15px}}.lib{{padding:12px 16px}}.libtabs{{display:flex;gap:22px;height:34px;align-items:center;margin-bottom:18px}}.libtabs .active{{background:#8737ff;color:white;border-radius:8px;padding:6px 10px;font-weight:800}}.asset{{width:118px;height:67px;border:2px solid #9638ff;border-radius:8px;overflow:hidden;background:#111}}.asset img{{width:100%;height:100%;object-fit:cover}}.right{{width:265px;padding:54px 12px}}.chips{{border:1px solid #dfe5ee;border-radius:10px;min-height:106px;padding:12px;margin-bottom:12px;display:flex;flex-wrap:wrap;gap:8px;align-content:flex-start}}.chip{{color:#944fff;background:#f1ddff;border-radius:999px;padding:6px 10px;font-weight:700}}.actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}.action{{height:40px;border:1px solid #caa4ff;border-radius:7px;color:#9344ff;background:white;font-weight:800}}.edit{{height:42px;margin-top:8px;width:100%;border:0;border-radius:8px;color:white;background:linear-gradient(90deg,#2f68ff,#b400ff);font-weight:900}}
</style>
</head>
<body>
<div class="top"><span>‹</span><div class="brand">绘梦工坊</div><div class="pill">剧本：<b>{escape(str(workspace.get("scriptName") or ""))}</b>⌄</div><div class="pill">剧集：<b>{escape(str(workspace.get("episodeLabel") or ""))}</b>⌄</div><div class="pill">风格：<b>{escape(str(workspace.get("style") or ""))}</b>⌄</div><div class="spacer"></div><div class="balance">积分余额：<b>{escape(str(workspace.get("pointsBalance") or ""))}</b></div><div class="user">{escape(str(workspace.get("username") or DEFAULT_MEDIA_ACCOUNT_NAME))}</div></div>
<div class="main"><aside class="side"><div class="side-head"><span>分镜表</span><span>{len(shots)} 个镜头</span></div><div class="list">{sidebar}</div></aside>
<section class="editor"><div class="editor-head"><span>{escape(title)}</span><span style="color:#8b95a7">{escape(summary_counter)}</span></div><div class="editor-body"><div class="section">分镜概要</div><div class="summary">{escape(summary)}</div><div class="section">画面要素</div><div class="grid"><div class="metric">角色 <b>{len(selected.get("characters") or [])}</b></div><div class="metric">场景 <b>{len(selected.get("scene") or [])}</b></div><div class="metric">道具 <b>{len(selected.get("props") or [])}</b></div></div><div class="grid"><div class="field">景别 <b>{escape(str(selected.get("shotSize") or "中景"))}</b>⌄</div><div class="field">角度 <b>{escape(str(selected.get("cameraAngle") or "平视"))}</b>⌄</div><div class="field">运镜 <b>{escape(str(selected.get("cameraMotion") or "固定"))}</b>⌄</div></div><div class="section">对话内容</div><div class="tabs"><div class="tab">文生图</div><div class="tab">图生图</div><div class="tab active">参考生视频</div><div class="tab">图生视频</div></div><div class="refs"><div class="add">＋<span>点击添加</span></div>{refs}</div><div class="prompt">先选择参考图片，然后描述您想生成的视频效果...</div><button class="btn">开始生成 ✧ 151</button></div></section>
<section class="preview"><div class="stage"><div class="player"><img src="{image_uri}"><div class="play">▶</div><div class="time">0:00 / 0:{duration:02d}</div></div></div><div class="lib"><div class="libtabs"><b>▦ 素材库</b><span class="active">当前分镜</span><span>所有分镜</span><span>全部</span><span>图片</span><span>视频</span><span>音频</span></div><div class="asset"><img src="{image_uri}"></div></div></section>
<aside class="right"><div class="chips"><span class="chip">Seedance 2.0</span><span class="chip">{escape(str(selected.get("aspectRatio") or ""))}</span><span class="chip">{duration}s</span><span class="chip">{escape(str(selected.get("resolution") or ""))}</span><span class="chip">{escape(str(selected.get("fps") or ""))}FPS</span></div><div class="actions"><button class="action">视频修改</button><button class="action">视频延长</button><button class="action">对口型-仅单人</button><button class="action">对口型-单人/多人</button><button class="action">超分</button><button class="action">插帧</button><button class="action">抽帧</button><button class="action">字幕擦除</button></div><button class="edit">↻　重新编辑</button></aside></div>
</body></html>"""


def render_sidebar_item(shot: dict[str, Any], keyframes_dir: Path, selected_index: int) -> str:
    index = int(shot["index"])
    image = (keyframes_dir / f"shot-{index:03d}.jpg").resolve().as_uri()
    active = " active" if index == selected_index else ""
    return (
        f'<div class="shot{active}"><img class="thumb" src="{image}">'
        f'<div style="min-width:0"><div class="shot-title">{escape(str(shot.get("title") or ""))}</div>'
        f'<div class="shot-meta">{escape(str(shot.get("summary") or ""))}</div></div></div>'
    )


def reference_indexes(selected_index: int, total: int) -> list[tuple[str, int]]:
    return [
        ("前一镜头", max(1, selected_index - 1)),
        ("当前镜头", selected_index),
        ("后一镜头", min(total, selected_index + 1)),
    ]


def render_ref_card(label: str, image_path: Path) -> str:
    return f'<div class="ref"><img src="{image_path.resolve().as_uri()}"><span>{escape(label)}</span></div>'


def normalize_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        text = str(item).strip()
        if text and text not in result:
            result.append(text)
    return result


def normalize_choice(value: object, allowed: list[str], fallback: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else fallback


def normalize_dialogues(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if text:
            result.append({"speaker": str(item.get("speaker") or "").strip(), "text": text})
    return result


def ffprobe_path_for(ffmpeg_path: str) -> str:
    ffmpeg = Path(ffmpeg_path)
    if ffmpeg.name == "ffmpeg":
        return str(ffmpeg.with_name("ffprobe")) if ffmpeg.parent != Path(".") else "ffprobe"
    if ffmpeg.name.startswith("ffmpeg"):
        return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe", 1)))
    return "ffprobe"


def resolve_chrome_path(chrome_path: str | None) -> str:
    if chrome_path:
        candidate = Path(chrome_path).expanduser()
        if candidate.exists():
            return str(candidate.resolve())
        resolved = shutil.which(chrome_path)
        if resolved:
            return resolved
    mac_default = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac_default.exists():
        return str(mac_default)
    resolved = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chrome")
    if resolved:
        return resolved
    raise StoryboardGenerationError("找不到 Chrome，无法生成分镜工程图。")


def parse_rate(value: object) -> float | None:
    text = str(value or "")
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        try:
            denominator_value = float(denominator)
            return float(numerator) / denominator_value if denominator_value else None
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


def aspect_ratio_label(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "9:16"
    ratio = width / height
    common = [("9:16", 9 / 16), ("16:9", 16 / 9), ("3:4", 3 / 4), ("4:3", 4 / 3), ("1:1", 1)]
    label, value = min(common, key=lambda item: abs(ratio - item[1]))
    if abs(ratio - value) < 0.05:
        return label
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def seconds_to_timecode(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}.{milliseconds:03d}"


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
    except subprocess.TimeoutExpired as exception:
        if success_path and success_path.exists() and success_path.stat().st_size > 0:
            return
        raise StoryboardGenerationError(f"{failure_message}：命令超时") from exception
    except subprocess.CalledProcessError as exception:
        if success_path and success_path.exists() and success_path.stat().st_size > 0:
            return
        detail = "\n".join(part for part in (exception.stderr, exception.stdout) if part)
        raise StoryboardGenerationError(f"{failure_message}：{detail[-1000:]}") from exception
    except OSError as exception:
        raise StoryboardGenerationError(f"{failure_message}：{exception}") from exception
