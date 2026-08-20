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


if __name__ == "__main__":
    unittest.main()
