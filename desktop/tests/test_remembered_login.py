from aidrama_desktop.auth.remembered_login import RememberedLoginStore


def test_remembered_login_expires_after_one_day(tmp_path):
    store = RememberedLoginStore(tmp_path / "remembered.json")

    store.set("user", "pass", now=1_000)

    assert store.get(now=1_000 + 24 * 60 * 60 - 1) == ("user", "pass")
    assert store.get(now=1_000 + 24 * 60 * 60 + 1) is None


def test_remembered_login_clear_removes_file(tmp_path):
    store = RememberedLoginStore(tmp_path / "remembered.json")

    store.set("user", "pass", now=1_000)
    store.clear()

    assert store.get(now=1_001) is None
