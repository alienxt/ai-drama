from aidrama_desktop.jianying import windows_uia_helper


def test_windows_uia_helper_opens_exact_full_description_parent(monkeypatch, tmp_path):
    state = {"clicked": False}

    class Bounds:
        left = 10
        top = 20
        right = 210
        bottom = 220

    class DraftCard:
        BoundingRectangle = Bounds()

        def Click(self, *, simulateMove):
            assert simulateMove is False
            state["clicked"] = True

    class DraftTitle:
        def __init__(self, compare):
            self.compare = compare

        def Exists(self, seconds, interval):
            assert (seconds, interval) == (20, 0.5)
            return self.compare(self, 2)

        def GetPropertyValue(self, property_id):
            assert property_id == 30159
            return "HomePageDraftTitle:测试工程"

        def GetParentControl(self):
            return DraftCard()

    class App:
        def __init__(self, status):
            self.Name = "剪映专业版"
            self.ClassName = "MainWindow" if status == "edit" else "HomePage"

        def Exists(self, _seconds):
            return True

        def SetActive(self):
            return None

        def SetTopmost(self, *_args):
            return None

        def TextControl(self, *, searchDepth, Compare):
            assert searchDepth == 2
            return DraftTitle(Compare)

    class Uia:
        def WindowControl(self, *, searchDepth, Compare):
            assert searchDepth == 1
            app = App("edit" if state["clicked"] else "home")
            assert Compare(app, 1)
            return app

    progress_path = tmp_path / "progress.log"
    monkeypatch.setattr(windows_uia_helper.sys, "platform", "win32")
    monkeypatch.setattr(windows_uia_helper, "_load_uiautomation", lambda: Uia())
    monkeypatch.setattr(windows_uia_helper.time, "sleep", lambda _seconds: None)

    windows_uia_helper.open_jianying_draft(
        r"C:\Jianying\JianyingPro.exe",
        "测试工程",
        windows_uia_helper.ProgressLog(progress_path),
    )

    progress = progress_path.read_text(encoding="utf-8")
    assert state["clicked"] is True
    assert "match=legacy" in progress
    assert "stage=python-uia-draft-title-observed" in progress
    assert "HomePageDraftTitle:测试工程" in progress
    assert "stage=python-uia-main-window-ready" in progress


def test_windows_uia_helper_waits_for_relaxed_process_window(monkeypatch, tmp_path):
    state = {"clicked": False, "window_exists_calls": 0}

    class Bounds:
        left = 11
        top = 22
        right = 211
        bottom = 222

    class DraftCard:
        BoundingRectangle = Bounds()

        def Click(self, *, simulateMove):
            assert simulateMove is False
            state["clicked"] = True

    class DraftTitle:
        def __init__(self, compare):
            self.compare = compare

        def Exists(self, seconds, interval):
            assert (seconds, interval) == (20, 0.5)
            return self.compare(self, 2)

        def GetPropertyValue(self, property_id):
            assert property_id == 30159
            return "HomePageDraftTitle:测试工程"

        def GetParentControl(self):
            return DraftCard()

    class App:
        ClassName = "Qt5152QWindowIcon"
        ProcessId = 42

        def __init__(self, compare):
            self.compare = compare

        @property
        def Name(self):
            return "测试工程 - JianyingPro" if state["clicked"] else "JianyingPro"

        def Exists(self, _seconds):
            state["window_exists_calls"] += 1
            matched = self.compare(self, 1)
            if state["window_exists_calls"] <= 2:
                return False
            return matched

        def SetActive(self):
            return None

        def SetTopmost(self, *_args):
            return None

        def TextControl(self, *, searchDepth, Compare):
            assert searchDepth == 2
            return DraftTitle(Compare)

    class Uia:
        def WindowControl(self, *, searchDepth, Compare):
            assert searchDepth == 1
            return App(Compare)

    progress_path = tmp_path / "progress.log"
    monkeypatch.setattr(windows_uia_helper.sys, "platform", "win32")
    monkeypatch.setattr(windows_uia_helper, "_load_uiautomation", lambda: Uia())
    monkeypatch.setattr(
        windows_uia_helper,
        "_process_image_path",
        lambda _pid: r"C:\duanju_ruanjian\JianyingPro\5.9.0.11632\JianyingPro.exe",
    )
    monkeypatch.setattr(windows_uia_helper.time, "sleep", lambda _seconds: None)

    windows_uia_helper.open_jianying_draft(
        r"C:\duanju_ruanjian\JianyingPro\5.9.0.11632\JianyingPro.exe",
        "测试工程",
        windows_uia_helper.ProgressLog(progress_path),
    )

    progress = progress_path.read_text(encoding="utf-8")
    assert state["clicked"] is True
    assert state["window_exists_calls"] > 1
    assert "match=relaxed" in progress
    assert "stage=python-uia-window-search-waiting" in progress
    assert "stage=python-uia-assume-home status=unknown" in progress
    assert "stage=python-uia-main-window-ready" in progress
