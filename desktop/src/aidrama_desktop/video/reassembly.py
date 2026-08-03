from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VIDEO_REASSEMBLY_METHOD_NONE = "none"
VIDEO_REASSEMBLY_METHOD_REASSEMBLE = "reassemble"


@dataclass(frozen=True)
class VideoReassemblyConfig:
    method: str = VIDEO_REASSEMBLY_METHOD_REASSEMBLE
    segment_min_seconds: float = 50.0
    segment_max_seconds: float = 60.0
    trim_head_seconds: float = 1.0
    trim_tail_seconds: float = 1.0
    speed_min_percent: float = 2.0
    speed_max_percent: float = 5.0
    swap_orientation: bool = False
    tail_merge_threshold_seconds: float = 30.0
    bgm_directory: str | None = None
    bgm_volume_percent: float = 8.0
    audio_pitch_semitones: float = 0.0
    border_percent: float = 0.0
    mirror_horizontal: bool = False
    rotate_degrees: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.method == VIDEO_REASSEMBLY_METHOD_REASSEMBLE

    def normalized(self) -> "VideoReassemblyConfig":
        method = self.method if self.method in {VIDEO_REASSEMBLY_METHOD_NONE, VIDEO_REASSEMBLY_METHOD_REASSEMBLE} else VIDEO_REASSEMBLY_METHOD_NONE
        segment_min = max(1.0, float(self.segment_min_seconds))
        segment_max = max(segment_min, float(self.segment_max_seconds))
        speed_min = float(self.speed_min_percent)
        speed_max = float(self.speed_max_percent)
        if speed_min > speed_max:
            speed_min, speed_max = speed_max, speed_min
        return VideoReassemblyConfig(
            method=method,
            segment_min_seconds=segment_min,
            segment_max_seconds=segment_max,
            trim_head_seconds=max(0.0, float(self.trim_head_seconds)),
            trim_tail_seconds=max(0.0, float(self.trim_tail_seconds)),
            speed_min_percent=max(-50.0, min(50.0, speed_min)),
            speed_max_percent=max(-50.0, min(50.0, speed_max)),
            swap_orientation=bool(self.swap_orientation),
            tail_merge_threshold_seconds=max(0.0, float(self.tail_merge_threshold_seconds)),
            bgm_directory=str(self.bgm_directory).strip() or None if self.bgm_directory is not None else None,
            bgm_volume_percent=max(0.0, min(100.0, float(self.bgm_volume_percent))),
            audio_pitch_semitones=max(-12.0, min(12.0, float(self.audio_pitch_semitones))),
            border_percent=max(0.0, min(20.0, float(self.border_percent))),
            mirror_horizontal=bool(self.mirror_horizontal),
            rotate_degrees=max(-10.0, min(10.0, float(self.rotate_degrees))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "segmentMinSeconds": self.segment_min_seconds,
            "segmentMaxSeconds": self.segment_max_seconds,
            "trimHeadSeconds": self.trim_head_seconds,
            "trimTailSeconds": self.trim_tail_seconds,
            "speedMinPercent": self.speed_min_percent,
            "speedMaxPercent": self.speed_max_percent,
            "swapOrientation": self.swap_orientation,
            "tailMergeThresholdSeconds": self.tail_merge_threshold_seconds,
            "bgmDirectory": self.bgm_directory,
            "bgmVolumePercent": self.bgm_volume_percent,
            "audioPitchSemitones": self.audio_pitch_semitones,
            "borderPercent": self.border_percent,
            "mirrorHorizontal": self.mirror_horizontal,
            "rotateDegrees": self.rotate_degrees,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoReassemblyConfig":
        return cls(
            method=str(data.get("method") or VIDEO_REASSEMBLY_METHOD_NONE),
            segment_min_seconds=float_value(data.get("segmentMinSeconds"), cls.segment_min_seconds),
            segment_max_seconds=float_value(data.get("segmentMaxSeconds"), cls.segment_max_seconds),
            trim_head_seconds=float_value(data.get("trimHeadSeconds"), cls.trim_head_seconds),
            trim_tail_seconds=float_value(data.get("trimTailSeconds"), cls.trim_tail_seconds),
            speed_min_percent=float_value(data.get("speedMinPercent"), cls.speed_min_percent),
            speed_max_percent=float_value(data.get("speedMaxPercent"), cls.speed_max_percent),
            swap_orientation=bool(data.get("swapOrientation", cls.swap_orientation)),
            tail_merge_threshold_seconds=float_value(
                data.get("tailMergeThresholdSeconds"),
                cls.tail_merge_threshold_seconds,
            ),
            bgm_directory=str(data.get("bgmDirectory") or "").strip() or None,
            bgm_volume_percent=float_value(data.get("bgmVolumePercent"), cls.bgm_volume_percent),
            audio_pitch_semitones=float_value(data.get("audioPitchSemitones"), cls.audio_pitch_semitones),
            border_percent=float_value(data.get("borderPercent"), cls.border_percent),
            mirror_horizontal=bool(data.get("mirrorHorizontal", cls.mirror_horizontal)),
            rotate_degrees=float_value(data.get("rotateDegrees"), cls.rotate_degrees),
        ).normalized()

    def summary(self) -> str:
        if not self.enabled:
            return "不启用"
        config = self.normalized()
        swap_text = "强制横竖互换并黑边填充" if config.swap_orientation else "保持原始横竖方向"
        bgm_text = (
            f"BGM目录已配置，音量{config.bgm_volume_percent:g}%"
            if config.bgm_directory
            else "不加BGM"
        )
        audio_fx = []
        if config.audio_pitch_semitones:
            audio_fx.append(f"音调{config.audio_pitch_semitones:g}半音")
        if config.mirror_horizontal:
            audio_fx.append("水平镜像")
        if config.rotate_degrees:
            audio_fx.append(f"旋转{config.rotate_degrees:g}°")
        if config.border_percent:
            audio_fx.append(f"黑边{config.border_percent:g}%")
        fx_text = "；".join(audio_fx) if audio_fx else "不加额外画面/音频扰动"
        speed_text = (
            f"变速{config.speed_min_percent:g}%"
            if config.speed_min_percent == config.speed_max_percent
            else f"变速{config.speed_min_percent:g}-{config.speed_max_percent:g}%"
        )
        return (
            "重组分集（全剧滚动切分；"
            "目标50-120集且不等于原下载集数；"
            f"切分{config.segment_min_seconds:g}-{config.segment_max_seconds:g}s；"
            f"去头{config.trim_head_seconds:g}s/尾{config.trim_tail_seconds:g}s；"
            f"{speed_text}；{swap_text}；{bgm_text}；{fx_text}）"
        )


class VideoReassemblyConfigStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> VideoReassemblyConfig:
        if not self.path.exists():
            return VideoReassemblyConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return VideoReassemblyConfig()
        if not isinstance(data, dict):
            return VideoReassemblyConfig()
        return VideoReassemblyConfig.from_dict(data)

    def save(self, config: VideoReassemblyConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(config.normalized().to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def float_value(value: object, default: float) -> float:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default
