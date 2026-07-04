import pytest
import httpx

from aidrama_desktop.api.client import ApiClient, ApiError, normalize_base_url
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


def test_api_client_hides_base_url_for_network_errors(tmp_path, monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, *args, **kwargs):
            request = httpx.Request("GET", "https://example.invalid/api/ping")
            raise httpx.ConnectError("failed to connect https://example.invalid/api/ping", request=request)

    monkeypatch.setattr(httpx, "Client", FailingClient)
    client = ApiClient("https://example.invalid/api", TokenStore(tmp_path / "token"))

    with pytest.raises(ApiError) as error:
        client.get("/ping")

    assert "无法连接服务" in str(error.value)
    assert "example.invalid" in str(error.value)
    assert "https://example.invalid/api/ping" not in str(error.value)
    assert "网络诊断" in str(error.value)
