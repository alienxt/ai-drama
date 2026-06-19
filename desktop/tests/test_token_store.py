from aidrama_desktop.api.client import normalize_base_url
from aidrama_desktop.auth.token_store import TokenStore


def test_token_store_roundtrip(tmp_path):
    store = TokenStore(tmp_path / "token")

    assert store.get() is None
    store.set("abc")

    assert store.get() == "abc"


def test_normalize_base_url_accepts_server_root_or_api_root():
    assert normalize_base_url("http://localhost:8080") == "http://localhost:8080/api"
    assert normalize_base_url("http://localhost:8080/") == "http://localhost:8080/api"
    assert normalize_base_url("http://localhost:8080/api") == "http://localhost:8080/api"
