import os
from datetime import datetime, timedelta, timezone

from aidrama_desktop.tasks.cache_cleanup import (
    UPLOAD_SUCCESS_MARKER,
    cleanup_uploaded_drama_cache,
    mark_upload_success,
)


def touch_tree(directory, when: datetime) -> None:
    timestamp = when.timestamp()
    os.utime(directory, (timestamp, timestamp))
    for path in directory.rglob("*"):
        os.utime(path, (timestamp, timestamp))


def test_cleanup_only_deletes_marked_uploaded_drama_dirs_after_retention(tmp_path):
    downloads = tmp_path / "dramas" / "downloads"
    processed = tmp_path / "dramas" / "processed"
    old_download = downloads / "drama-old"
    old_processed = processed / "drama-old"
    fresh_download = downloads / "drama-fresh"
    unmarked_download = downloads / "drama-unmarked"
    unrelated_file = downloads / "readme.txt"

    for directory in (old_download, old_processed, fresh_download, unmarked_download):
        directory.mkdir(parents=True)
        (directory / "001.mp4").write_bytes(b"video")
    unrelated_file.write_text("keep", encoding="utf-8")

    now = datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc)
    mark_upload_success(
        old_download,
        drama_id="drama-1",
        task_id="task-1",
        platform="WECHAT_VIDEO",
        platform_publish_id="pub-1",
        uploaded_at=now - timedelta(hours=25),
    )
    mark_upload_success(
        old_processed,
        drama_id="drama-1",
        task_id="task-1",
        platform="WECHAT_VIDEO",
        platform_publish_id="pub-1",
        uploaded_at=now - timedelta(hours=25),
    )
    mark_upload_success(
        fresh_download,
        drama_id="drama-2",
        task_id="task-2",
        platform="WECHAT_VIDEO",
        platform_publish_id="pub-2",
        uploaded_at=now - timedelta(hours=23),
    )
    touch_tree(unmarked_download, now - timedelta(hours=1))

    result = cleanup_uploaded_drama_cache(downloads, processed, now=now)

    assert result.deleted_dirs == 2
    assert result.errors == ()
    assert not old_download.exists()
    assert not old_processed.exists()
    assert fresh_download.exists()
    assert (fresh_download / UPLOAD_SUCCESS_MARKER).exists()
    assert unmarked_download.exists()
    assert unrelated_file.exists()
    assert downloads.exists()
    assert processed.exists()


def test_cleanup_deletes_unmarked_stale_drama_dirs_after_retention(tmp_path):
    downloads = tmp_path / "dramas" / "downloads"
    processed = tmp_path / "dramas" / "processed"
    old_download = downloads / "drama-old"
    fresh_processed = processed / "drama-fresh"
    protected_download = downloads / "drama-protected"
    protected_nested = protected_download / "reassembled"

    for directory in (old_download, fresh_processed, protected_nested):
        directory.mkdir(parents=True)
        (directory / "001.mp4").write_bytes(b"video")

    now = datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc)
    touch_tree(old_download, now - timedelta(hours=49))
    touch_tree(fresh_processed, now - timedelta(hours=47, minutes=59))
    touch_tree(protected_download, now - timedelta(hours=72))

    result = cleanup_uploaded_drama_cache(
        downloads,
        processed,
        now=now,
        protected_dirs=[protected_nested],
    )

    assert result.deleted_dirs == 1
    assert result.errors == ()
    assert not old_download.exists()
    assert fresh_processed.exists()
    assert protected_download.exists()


def test_cleanup_refuses_nested_or_external_paths(tmp_path):
    downloads = tmp_path / "dramas" / "downloads"
    processed = tmp_path / "dramas" / "processed"
    drama_dir = downloads / "drama-old"
    nested_dir = drama_dir / "nested"
    drama_dir.mkdir(parents=True)
    nested_dir.mkdir()
    (nested_dir / "001.mp4").write_bytes(b"video")
    mark_upload_success(
        nested_dir,
        drama_id="drama-1",
        task_id="task-1",
        platform="WECHAT_VIDEO",
        platform_publish_id="pub-1",
        uploaded_at=datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc),
    )

    result = cleanup_uploaded_drama_cache(
        downloads,
        processed,
        now=datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc),
    )

    assert result.deleted_dirs == 0
    assert drama_dir.exists()
    assert nested_dir.exists()


def test_cleanup_ignores_roots_that_do_not_match_drama_cache_shape(tmp_path):
    downloads = tmp_path / "Downloads"
    processed = tmp_path / "processed"
    old_download = downloads / "drama-old"
    old_processed = processed / "drama-old"
    for directory in (old_download, old_processed):
        directory.mkdir(parents=True)
        (directory / "001.mp4").write_bytes(b"video")
        mark_upload_success(
            directory,
            drama_id="drama-1",
            task_id="task-1",
            platform="WECHAT_VIDEO",
            platform_publish_id="pub-1",
            uploaded_at=datetime(2026, 7, 26, 22, 0, tzinfo=timezone.utc),
        )

    result = cleanup_uploaded_drama_cache(
        downloads,
        processed,
        now=datetime(2026, 7, 28, 23, 0, tzinfo=timezone.utc),
    )

    assert result.deleted_dirs == 0
    assert old_download.exists()
    assert old_processed.exists()
