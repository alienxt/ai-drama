from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from aidrama_desktop.auth.token_store import TokenStore

API_REQUEST_TIMEOUT_SECONDS = 300


class ApiError(RuntimeError):
    pass


def normalize_base_url(base_url: str) -> str:
    clean = base_url.strip().rstrip("/")
    if clean.endswith("/api"):
        return clean
    return f"{clean}/api"


@dataclass
class ApiClient:
    base_url: str
    token_store: TokenStore

    def __post_init__(self) -> None:
        self.base_url = normalize_base_url(self.base_url)

    def _headers(self) -> dict[str, str]:
        token = self.token_store.get()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def download_headers(self) -> dict[str, str]:
        return self._headers()

    def login(self, username: str, password: str, device_id: str | None = None) -> None:
        payload = {"username": username, "password": password}
        if device_id:
            payload["deviceId"] = device_id
        data = self.post("/auth/login", payload, auth=False)
        self.token_store.set(data["token"])

    def get(self, path: str) -> Any:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any] | None = None, auth: bool = True) -> Any:
        return self._request("POST", path, payload, auth=auth)

    def put(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request("PUT", path, payload)

    def patch(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        return self._request("PATCH", path, payload)

    def check_update(self, platform: str, current_version: str) -> Any:
        query = urlencode({"platform": platform, "currentVersion": current_version})
        return self.get(f"/desktop/versions/check?{query}")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        headers = self._headers() if auth else {}
        try:
            with httpx.Client(base_url=self.base_url, timeout=API_REQUEST_TIMEOUT_SECONDS) as client:
                response = client.request(method, path, json=payload, headers=headers)
        except httpx.TimeoutException as exception:
            raise ApiError("服务请求超时，请稍后重试。") from exception
        except httpx.RequestError as exception:
            raise ApiError(connection_error_message(self.base_url, exception)) from exception
        body = self._parse_body(response)
        if getattr(response, "status_code", 200) >= 400:
            raise ApiError(self._error_message(response, body))
        if not body.get("success"):
            error = body.get("error") or {}
            raise ApiError(error.get("message", "API request failed"))
        return body.get("data")

    @staticmethod
    def _parse_body(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _error_message(response: httpx.Response, body: dict[str, Any]) -> str:
        error = body.get("error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        if message:
            return str(message)
        messages = {
            400: "请求参数有误，请检查后重试。",
            401: "登录失败，请检查用户名和密码。",
            403: "没有权限访问服务，请确认账号是否已绑定当前设备。",
            404: "服务地址不正确，未找到对应接口。",
            500: "服务端异常，请稍后重试或联系管理员。",
            504: "服务端处理超时，任务可能仍在后台执行。请刷新任务列表，必要时先强停再重试。",
        }
        status_code = getattr(response, "status_code", 0)
        return messages.get(status_code, f"服务请求失败（HTTP {status_code}）。")


def connection_error_message(base_url: str, exception: httpx.RequestError) -> str:
    host = urlparse(base_url).hostname or "服务地址"
    detail = _connection_error_detail(exception)
    return f"无法连接服务：{host} {detail}。可以断开 WireGuard 后点击登录页“网络诊断”，再把报告发给管理员。"


def _connection_error_detail(exception: httpx.RequestError) -> str:
    raw = _exception_chain_text(exception).lower()
    if any(token in raw for token in ("getaddrinfo", "name or service not known", "nodename nor servname")):
        return "域名解析失败"
    if "temporary failure in name resolution" in raw:
        return "DNS 临时解析失败"
    if "network is unreachable" in raw:
        return "当前网络不可达"
    if "connection refused" in raw:
        return "服务器拒绝连接"
    if "certificate" in raw or "ssl" in raw:
        return "证书校验失败"
    if "timed out" in raw or "timeout" in raw:
        return "连接超时"
    message = str(exception).strip()
    if "http://" in message or "https://" in message:
        return f"连接失败（{exception.__class__.__name__}）"
    return message or exception.__class__.__name__


def _exception_chain_text(exception: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exception
    while current is not None:
        parts.append(f"{current.__class__.__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " | ".join(parts)
