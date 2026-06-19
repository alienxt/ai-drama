from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse


Headers = dict[str, str]
AgentResponse = tuple[int, Headers, bytes]


def build_agent_response(
    method: str,
    path: str,
    open_media: Callable[[str, str | None], None],
) -> AgentResponse:
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }
    if method == "OPTIONS":
        return 204, cors, b""

    parsed = urlparse(path)
    if method == "GET" and parsed.path == "/health":
        return 200, cors, b'{"success": true}'

    if method == "GET" and parsed.path == "/open-media":
        query = parse_qs(parsed.query)
        platform = query.get("platform", ["WECHAT_VIDEO"])[0]
        account_id = query.get("accountId", [None])[0]
        open_media(platform, account_id)
        return 200, cors, b'{"success": true}'

    return 404, cors, b'{"success": false}'


def create_local_agent_server(port: int, open_media: Callable[[str, str | None], None]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # noqa: N802
            self._send("OPTIONS")

        def do_GET(self) -> None:  # noqa: N802
            self._send("GET")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, method: str) -> None:
            status, headers, body = build_agent_response(method, self.path, open_media)
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            if body:
                self.wfile.write(body)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_local_agent(port: int, open_media: Callable[[str, str | None], None]) -> None:
    create_local_agent_server(port, open_media).serve_forever()
