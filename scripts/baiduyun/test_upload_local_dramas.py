import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().with_name("upload_local_dramas.py")
SPEC = importlib.util.spec_from_file_location("upload_local_dramas", SCRIPT_PATH)
uploader = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["upload_local_dramas"] = uploader
SPEC.loader.exec_module(uploader)


class UploadLocalDramasTest(unittest.TestCase):
    def test_disable_windows_quick_edit_mode_is_noop_off_windows(self):
        self.assertFalse(uploader.disable_windows_quick_edit_mode())

    def test_build_plan_from_video_info(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "白龙渡恩记"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text(
                "\ufeff视频信息记录\n\n"
                "名称：白龙渡恩记\n"
                "作者：鱼阅文化\n"
                "分类：剧情\n"
                "集数：2\n"
                "时长：53.48分钟 秒\n\n"
                "简介：\n"
                "三十年前，魏守义救下搁浅小白龙。\n"
                "多年后白龙现身报恩。\n\n"
                "演员信息：\n"
                "演员：\n",
                encoding="utf-8",
            )
            (drama_dir / "海报.jpg").write_bytes(b"jpg")
            (drama_dir / "第02集.mp4").write_bytes(b"two")
            (drama_dir / "第01集.mp4").write_bytes(b"one")

            plan = uploader.build_drama_plan(drama_dir, "/drama/真人剧/2026", "8月18日")

            self.assertEqual(plan.title, "白龙渡恩记")
            self.assertEqual(plan.author, "鱼阅文化")
            self.assertEqual(plan.category, "剧情")
            self.assertEqual(plan.episode_count, 2)
            self.assertEqual(plan.cover_remote_name, "封面.jpg")
            self.assertEqual([episode.remote_name for episode in plan.episodes], ["第01集.mp4", "第02集.mp4"])
            self.assertEqual(plan.remote_dir, "/drama/真人剧/2026/8月18日/白龙渡恩记（2集）")
            self.assertIn("三十年前", plan.summary)
            self.assertNotIn("演员信息", plan.summary)

    def test_missing_episode_is_rejected_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "少一集"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：少一集\n集数：2\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")

            with self.assertRaisesRegex(uploader.UploadError, "missing episode files"):
                uploader.build_drama_plan(drama_dir, "/root", "8月18日")

    def test_download_temp_file_marks_directory_incomplete(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "还在下载"
            drama_dir.mkdir()
            (drama_dir / "第01集.mp4").write_bytes(b"one")
            (drama_dir / "第02集.mp4.part").write_bytes(b"partial")

            self.assertFalse(uploader.is_download_complete(drama_dir, checks=1, interval_seconds=0))

    def test_info_episode_count_marks_download_ready(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "已下载"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：已下载\n集数：2\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")
            (drama_dir / "第02集.mp4").write_bytes(b"two")

            readiness = uploader.download_readiness(drama_dir)

            self.assertTrue(readiness.ready)
            self.assertTrue(readiness.used_info_count)
            self.assertEqual(readiness.reason, "episode files complete 2/2")

    def test_info_episode_count_waits_for_missing_episode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "还少一集"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：还少一集\n集数：2\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")

            readiness = uploader.download_readiness(drama_dir)

            self.assertFalse(readiness.ready)
            self.assertEqual(readiness.reason, "episode files 1/2, missing 2")

    def test_info_episode_count_rejects_extra_episode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "多了一集"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：多了一集\n集数：2\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")
            (drama_dir / "第02集.mp4").write_bytes(b"two")
            (drama_dir / "第03集.mp4").write_bytes(b"three")

            readiness = uploader.download_readiness(drama_dir)

            self.assertFalse(readiness.ready)
            self.assertEqual(readiness.reason, "episode files 3/2")

    def test_ensure_quota_available_rejects_insufficient_space(self):
        original_request_json = uploader.request_json
        uploader.request_json = lambda *_args, **_kwargs: {"errno": 0, "total": 100, "used": 90}
        try:
            with self.assertRaisesRegex(uploader.UploadError, "quota is not enough"):
                uploader.ensure_quota_available("token", 20)
        finally:
            uploader.request_json = original_request_json

    def test_connection_reset_is_wrapped_as_retryable_upload_error(self):
        original_urlopen = uploader.urlopen

        def raise_connection_reset(*_args, **_kwargs):
            raise ConnectionResetError(10054, "远程主机强迫关闭了一个现有的连接。")

        uploader.urlopen = raise_connection_reset
        try:
            with self.assertRaisesRegex(uploader.UploadError, "Network error"):
                uploader.request_json("https://d.pcs.baidu.com/rest/2.0/pcs/superfile2")
        finally:
            uploader.urlopen = original_urlopen

    def test_upload_file_can_use_cached_existing_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "one.txt"
            local_path.write_bytes(b"one")
            original_remote_entry = uploader.remote_entry

            def fail_remote_entry(*_args, **_kwargs):
                raise AssertionError("remote_entry should not be called")

            uploader.remote_entry = fail_remote_entry
            try:
                result = uploader.upload_file(
                    "token",
                    local_path,
                    "/remote/one.txt",
                    existing_entry={"size": local_path.stat().st_size},
                    skip_remote_check=True,
                )
            finally:
                uploader.remote_entry = original_remote_entry

            self.assertEqual(result, "/remote/one.txt")

    def test_upload_file_retries_transient_create_errno(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "one.txt"
            local_path.write_bytes(b"one")
            original_api_post_form_json = uploader.api_post_form_json
            original_upload_block = uploader.upload_block
            original_locate_upload_url = uploader.locate_upload_url
            original_upload_direct_small_file = uploader.upload_direct_small_file
            original_sleep = uploader.time.sleep
            create_attempts = 0

            def fake_api_post_form_json(_url, params, form, **_kwargs):
                nonlocal create_attempts
                if params["method"] == "precreate":
                    return {"uploadid": "upload-1", "block_list": [0]}
                if params["method"] == "create":
                    create_attempts += 1
                    if create_attempts == 1:
                        raise uploader.UploadError('Baidu API error -10: {"errno": -10, "path": ""}')
                    return {"path": form["path"]}
                raise AssertionError(f"unexpected method: {params['method']}")

            uploader.api_post_form_json = fake_api_post_form_json
            uploader.upload_block = lambda *_args, **_kwargs: {"md5": "ok"}
            uploader.locate_upload_url = lambda *_args, **_kwargs: "https://upload.example.com/rest/2.0/pcs/superfile2"
            uploader.upload_direct_small_file = lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("direct upload should not run when create retry succeeds")
            )
            uploader.time.sleep = lambda _seconds: None
            try:
                result = uploader.upload_file(
                    "token",
                    local_path,
                    "/remote/one.txt",
                    on_duplicate="skip",
                    retries=1,
                    skip_remote_check=True,
                )
            finally:
                uploader.api_post_form_json = original_api_post_form_json
                uploader.upload_block = original_upload_block
                uploader.locate_upload_url = original_locate_upload_url
                uploader.upload_direct_small_file = original_upload_direct_small_file
                uploader.time.sleep = original_sleep

            self.assertEqual(result, "/remote/one.txt")
            self.assertEqual(create_attempts, 2)

    def test_upload_file_falls_back_to_direct_upload_for_small_file_create_errno(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "one.txt"
            local_path.write_bytes(b"one")
            original_api_post_form_json = uploader.api_post_form_json
            original_upload_block = uploader.upload_block
            original_locate_upload_url = uploader.locate_upload_url
            original_upload_direct_small_file = uploader.upload_direct_small_file
            original_sleep = uploader.time.sleep
            direct_attempts = 0

            def fake_api_post_form_json(_url, params, form, **_kwargs):
                if params["method"] == "precreate":
                    return {"uploadid": "upload-1", "block_list": [0]}
                if params["method"] == "create":
                    raise uploader.UploadError('Baidu API error -10: {"errno": -10, "path": ""}')
                raise AssertionError(f"unexpected method: {params['method']}")

            def fake_upload_direct_small_file(_token, _local_path, remote_path, **_kwargs):
                nonlocal direct_attempts
                direct_attempts += 1
                return {"path": remote_path}

            uploader.api_post_form_json = fake_api_post_form_json
            uploader.upload_block = lambda *_args, **_kwargs: {"md5": "ok"}
            uploader.locate_upload_url = lambda *_args, **_kwargs: "https://upload.example.com/rest/2.0/pcs/superfile2"
            uploader.upload_direct_small_file = fake_upload_direct_small_file
            uploader.time.sleep = lambda _seconds: None
            try:
                result = uploader.upload_file(
                    "token",
                    local_path,
                    "/remote/one.txt",
                    on_duplicate="skip",
                    retries=1,
                    skip_remote_check=True,
                )
            finally:
                uploader.api_post_form_json = original_api_post_form_json
                uploader.upload_block = original_upload_block
                uploader.locate_upload_url = original_locate_upload_url
                uploader.upload_direct_small_file = original_upload_direct_small_file
                uploader.time.sleep = original_sleep

            self.assertEqual(result, "/remote/one.txt")
            self.assertEqual(direct_attempts, 1)

    def test_upload_file_returns_when_precreate_rapid_upload_succeeds(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / "one.txt"
            local_path.write_bytes(b"one")
            original_api_post_form_json = uploader.api_post_form_json
            original_upload_block = uploader.upload_block

            def fake_api_post_form_json(_url, params, form, **_kwargs):
                if params["method"] == "precreate":
                    return {"return_type": 2, "path": form["path"]}
                raise AssertionError(f"unexpected method: {params['method']}")

            def fail_upload_block(*_args, **_kwargs):
                raise AssertionError("rapid upload should not upload blocks")

            uploader.api_post_form_json = fake_api_post_form_json
            uploader.upload_block = fail_upload_block
            try:
                result = uploader.upload_file(
                    "token",
                    local_path,
                    "/remote/one.txt",
                    on_duplicate="skip",
                    skip_remote_check=True,
                )
            finally:
                uploader.api_post_form_json = original_api_post_form_json
                uploader.upload_block = original_upload_block

            self.assertEqual(result, "/remote/one.txt")

    def test_upload_drama_plan_continues_when_summary_upload_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "简介失败"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：简介失败\n集数：1\n简介：能导入即可\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")
            plan = uploader.build_drama_plan(drama_dir, "/root", "8月20日")

            original_ensure_remote_dir = uploader.ensure_remote_dir
            original_remote_entries_by_path = uploader.remote_entries_by_path
            original_upload_bytes = uploader.upload_bytes
            original_upload_file = uploader.upload_file

            def fake_upload_bytes(*_args, **_kwargs):
                raise uploader.UploadError("Baidu API error -10")

            uploader.ensure_remote_dir = lambda *_args, **_kwargs: None
            uploader.remote_entries_by_path = lambda *_args, **_kwargs: {}
            uploader.upload_bytes = fake_upload_bytes
            uploader.upload_file = lambda _token, _path, remote_path, **_kwargs: remote_path
            try:
                marker = uploader.upload_drama_plan(
                    "token",
                    plan,
                    on_duplicate="skip",
                    timeout=1,
                    retries=0,
                    write_marker=False,
                )
            finally:
                uploader.ensure_remote_dir = original_ensure_remote_dir
                uploader.remote_entries_by_path = original_remote_entries_by_path
                uploader.upload_bytes = original_upload_bytes
                uploader.upload_file = original_upload_file

            self.assertEqual(marker["uploadedFiles"], ["/root/8月20日/简介失败（1集）/第01集.mp4"])
            self.assertIn("metadataUploadFailures", marker)

    def test_upload_drama_plan_keeps_episode_order_with_workers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            drama_dir = Path(tmpdir) / "并发上传"
            drama_dir.mkdir()
            (drama_dir / "视频信息.txt").write_text("名称：并发上传\n集数：3\n", encoding="utf-8")
            (drama_dir / "第01集.mp4").write_bytes(b"one")
            (drama_dir / "第02集.mp4").write_bytes(b"two")
            (drama_dir / "第03集.mp4").write_bytes(b"three")
            plan = uploader.build_drama_plan(drama_dir, "/root", "8月20日")

            original_ensure_remote_dir = uploader.ensure_remote_dir
            original_remote_entries_by_path = uploader.remote_entries_by_path
            original_upload_bytes = uploader.upload_bytes
            original_upload_file = uploader.upload_file
            file_calls = []

            def fake_ensure_remote_dir(*_args, **_kwargs):
                return None

            def fake_remote_entries_by_path(*_args, **_kwargs):
                return {}

            def fake_upload_bytes(_access_token, _content, remote_path, **_kwargs):
                return remote_path

            def fake_upload_file(_access_token, _local_path, remote_path, **kwargs):
                file_calls.append((remote_path, kwargs.get("skip_remote_check")))
                return remote_path

            uploader.ensure_remote_dir = fake_ensure_remote_dir
            uploader.remote_entries_by_path = fake_remote_entries_by_path
            uploader.upload_bytes = fake_upload_bytes
            uploader.upload_file = fake_upload_file
            try:
                marker = uploader.upload_drama_plan(
                    "token",
                    plan,
                    on_duplicate="skip",
                    timeout=1,
                    retries=0,
                    write_marker=False,
                    upload_workers=2,
                )
            finally:
                uploader.ensure_remote_dir = original_ensure_remote_dir
                uploader.remote_entries_by_path = original_remote_entries_by_path
                uploader.upload_bytes = original_upload_bytes
                uploader.upload_file = original_upload_file

            self.assertEqual(
                marker["uploadedFiles"],
                [
                    "/root/8月20日/并发上传（3集）/简介.txt",
                    "/root/8月20日/并发上传（3集）/第01集.mp4",
                    "/root/8月20日/并发上传（3集）/第02集.mp4",
                    "/root/8月20日/并发上传（3集）/第03集.mp4",
                ],
            )
            self.assertTrue(all(skip_remote_check for _remote_path, skip_remote_check in file_calls))


if __name__ == "__main__":
    unittest.main()
