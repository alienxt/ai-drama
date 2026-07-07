import pytest
import httpx

from aidrama_desktop.api.client import ApiClient, ApiError, connection_error_message


class Store:
    def __init__(self):
        self.token = None

    def get(self):
        return self.token

    def set(self, token):
        self.token = token


def test_login_sends_device_id(monkeypatch):
    requests = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"success": True, "data": {"token": "token-1"}, "error": None}

    class Client:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, path, json=None, headers=None):
            requests.append((method, path, json, headers))
            return Response()

    monkeypatch.setattr("aidrama_desktop.api.client.httpx.Client", Client)
    store = Store()
    client = ApiClient("http://server/api", store)

    client.login("u", "p", "device-1")

    assert requests == [("POST", "/auth/login", {"username": "u", "password": "p", "deviceId": "device-1"}, {})]
    assert store.token == "token-1"


def test_login_uses_api_error_message_from_forbidden_response(monkeypatch):
    class Response:
        status_code = 403

        def json(self):
            return {
                "success": False,
                "data": None,
                "error": {
                    "code": "DEVICE_MISMATCH",
                    "message": "账号已绑定其他设备，不允许在当前设备登录",
                },
            }

        def raise_for_status(self):
            raise AssertionError("should parse API error before raising HTTPStatusError")

    class Client:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, path, json=None, headers=None):
            return Response()

    monkeypatch.setattr("aidrama_desktop.api.client.httpx.Client", Client)
    client = ApiClient("http://server/api", Store())

    with pytest.raises(ApiError, match="账号已绑定其他设备"):
        client.login("u", "p", "device-1")


def test_login_shows_friendly_message_for_non_json_forbidden_response(monkeypatch):
    class Response:
        status_code = 403

        def json(self):
            raise ValueError("not json")

        def raise_for_status(self):
            raise AssertionError("should map HTTP 403 without leaking httpx docs")

    class Client:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, path, json=None, headers=None):
            return Response()

    monkeypatch.setattr("aidrama_desktop.api.client.httpx.Client", Client)
    client = ApiClient("http://server/api", Store())

    with pytest.raises(ApiError) as error:
        client.login("u", "p", "device-1")

    assert str(error.value) == "没有权限访问服务，请确认账号是否已绑定当前设备。"


def test_check_update_sends_platform_and_current_version(monkeypatch):
    requests = []

    class Response:
        status_code = 200

        def json(self):
            return {"success": True, "data": {"updateAvailable": False}, "error": None}

    class Client:
        def __init__(self, base_url, timeout):
            self.base_url = base_url
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def request(self, method, path, json=None, headers=None):
            requests.append((method, path, json, headers))
            return Response()

    monkeypatch.setattr("aidrama_desktop.api.client.httpx.Client", Client)
    store = Store()
    store.token = "token-1"
    client = ApiClient("http://server/api", store)

    assert client.check_update("MAC", "0.1.0") == {"updateAvailable": False}
    assert requests == [
        (
            "GET",
            "/desktop/versions/check?platform=MAC&currentVersion=0.1.0",
            None,
            {"Authorization": "Bearer token-1"},
        )
    ]


def test_connection_error_message_keeps_useful_reason():
    error = httpx.ConnectError("nodename nor servname provided")

    message = connection_error_message("http://ai-drama-admin-1807108618.ap-southeast-1.elb.amazonaws.com/api", error)

    assert "无法连接服务" in message
    assert "ai-drama-admin-1807108618.ap-southeast-1.elb.amazonaws.com" in message
    assert "域名解析失败" in message
    assert "网络诊断" in message
