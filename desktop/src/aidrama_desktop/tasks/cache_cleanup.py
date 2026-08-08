from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


UPLOAD_SUCCESS_MARKER = ".aidrama-upload-success.json"
DEFAULT_UPLOAD_CACHE_RETENTION = timedelta(hours=48)
DEFAULT_STALE_CACHE_RETENTION = timedelta(hours=48)


@dataclass(frozen=True)
class UploadCacheCleanupResult:
    scanned_dirs: int = 0
    deleted_dirs: int = 0
    bytes_deleted: int = 0
    skipped_dirs: int = 0
    errors: tuple[str, ...] = ()


def mark_upload_success(
    directory: Path,
    *,
    drama_id: str | None,
    task_id: str | None,
    platform: str | None,
    platform_publish_id: str | None,
    uploaded_at: datetime | None = None,
) -> bool:
    if not directory.is_dir() or directory.is_symlink():
        return False
    payload = {
        "version": 1,
        "dramaId": drama_id,
        "taskId": task_id,
        "platform": platform,
        "platformPublishId": platform_publish_id,
        "uploadedAt": _format_timestamp(uploaded_at or _utc_now()),
    }
    marker = directory / UPLOAD_SUCCESS_MARKER
    marker_tmp = marker.with_name(f"{marker.name}.tmp")
    marker_tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    marker_tmp.replace(marker)
    return True


def cleanup_uploaded_drama_cache(
    downloads_dir: Path,
    processed_dir: Path,
    *,
    now: datetime | None = None,
    retention: timedelta = DEFAULT_UPLOAD_CACHE_RETENTION,
    stale_retention: timedelta = DEFAULT_STALE_CACHE_RETENTION,
    protected_dirs: Iterable[Path] | None = None,
) -> UploadCacheCleanupResult:
    now = now or _utc_now()
    roots = _safe_cache_roots(downloads_dir, processed_dir)
    protected = _protected_cache_dirs(protected_dirs)
    scanned = 0
    deleted = 0
    skipped = 0
    bytes_deleted = 0
    errors: list[str] = []

    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        root_resolved = root.resolve(strict=False)
        for child in root.iterdir():
            if not child.is_dir() or child.is_symlink():
                skipped += 1
                continue
            scanned += 1
            if _is_protected_dir(child, protected):
                skipped += 1
                continue
            marker = child / UPLOAD_SUCCESS_MARKER
            if marker.is_file():
                try:
                    cache_at = _marker_uploaded_at(marker)
                except (OSError, ValueError, json.JSONDecodeError) as exception:
                    skipped += 1
                    errors.append(f"{child}: {exception}")
                    continue
                effective_retention = retention
            else:
                try:
                    cache_at = _directory_latest_modified_at(child)
                except OSError as exception:
                    skipped += 1
                    errors.append(f"{child}: {exception}")
                    continue
                effective_retention = stale_retention
            if now - cache_at < effective_retention:
                skipped += 1
                continue
            if not _is_direct_child_of(child, root_resolved):
                skipped += 1
                errors.append(f"{child}: refused to delete outside cache root")
                continue
            try:
                size = _directory_size(child)
                shutil.rmtree(child)
            except OSError as exception:
                skipped += 1
                errors.append(f"{child}: {exception}")
                continue
            deleted += 1
            bytes_deleted += size

    return UploadCacheCleanupResult(
        scanned_dirs=scanned,
        deleted_dirs=deleted,
        bytes_deleted=bytes_deleted,
        skipped_dirs=skipped,
        errors=tuple(errors),
    )


def _marker_uploaded_at(marker: Path) -> datetime:
    payload = json.loads(marker.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid upload marker")
    value = payload.get("uploadedAt")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("upload marker missing uploadedAt")
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _protected_cache_dirs(protected_dirs: Iterable[Path] | None) -> tuple[Path, ...]:
    if not protected_dirs:
        return ()
    protected: list[Path] = []
    for path in protected_dirs:
        try:
            protected.append(Path(path).expanduser().resolve(strict=False))
        except OSError:
            continue
    return tuple(protected)


def _is_protected_dir(directory: Path, protected_dirs: tuple[Path, ...]) -> bool:
    if not protected_dirs:
        return False
    directory_resolved = directory.resolve(strict=False)
    for protected in protected_dirs:
        if directory_resolved == protected:
            return True
        try:
            protected.relative_to(directory_resolved)
        except ValueError:
            continue
        return True
    return False


def _safe_cache_roots(downloads_dir: Path, processed_dir: Path) -> list[Path]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for root, expected_name in ((downloads_dir, "downloads"), (processed_dir, "processed")):
        expanded = Path(root).expanduser()
        if expanded.name != expected_name or expanded.parent.name != "dramas":
            continue
        if expanded.is_symlink() or not expanded.is_dir():
            continue
        normalized = expanded.resolve(strict=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(expanded)
    return unique


def _is_direct_child_of(path: Path, root_resolved: Path) -> bool:
    try:
        relative = path.resolve(strict=False).relative_to(root_resolved)
    except ValueError:
        return False
    return len(relative.parts) == 1 and relative.parts[0] not in {"", ".", ".."}


def _directory_size(directory: Path) -> int:
    total = 0
    for path in directory.rglob("*"):
        if path.is_file() and not path.is_symlink():
            try:
                total += path.stat().st_size
            except OSError:
                continue
    return total


def _directory_latest_modified_at(directory: Path) -> datetime:
    latest = directory.stat().st_mtime
    for path in directory.rglob("*"):
        if path.is_symlink():
            continue
        try:
            latest = max(latest, path.stat().st_mtime)
        except OSError:
            continue
    return datetime.fromtimestamp(latest, timezone.utc)
