import socket
from pathlib import Path

import httpx

from aidrama_desktop.api.diagnostics import diagnose_server, write_diagnostic_report


def test_diagnose_server_treats_http_forbidden_as_reachable(monkeypatch):
    requested_urls = []

    def fake_getaddrinfo(host, port, type):
        assert host == "ad.ai-drama.uk"
        assert port == 443
        assert type == socket.SOCK_STREAM
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("104.21.37.225", port))]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_create_connection(target, timeout):
        assert target == ("104.21.37.225", 443)
        assert timeout > 0
        return FakeConnection()

    class Response:
        status_code = 403
        headers = {"server": "cloudflare", "cf-ray": "trace-1"}

    class Client:
        def __init__(self, timeout, follow_redirects):
            self.timeout = timeout
            self.follow_redirects = follow_redirects

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            requested_urls.append(url)
            return Response()

    monkeypatch.setattr("aidrama_desktop.api.diagnostics.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("aidrama_desktop.api.diagnostics.socket.create_connection", fake_create_connection)
    monkeypatch.setattr("aidrama_desktop.api.diagnostics.httpx.Client", Client)

    report = diagnose_server("https://ad.ai-drama.uk/api")

    assert report.healthy is True
    assert "服务地址可以连通" in report.conclusion
    assert "desktop/versions/check" in requested_urls[0]
    assert "HTTP 403" in report.to_text()


def test_diagnose_server_identifies_dns_failure(monkeypatch):
    def fake_getaddrinfo(host, port, type):
        raise socket.gaierror("nodename nor servname provided")

    class Client:
        def __init__(self, timeout, follow_redirects):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            raise httpx.ConnectError("nodename nor servname provided")

    monkeypatch.setattr("aidrama_desktop.api.diagnostics.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("aidrama_desktop.api.diagnostics.httpx.Client", Client)

    report = diagnose_server("https://ad.ai-drama.uk/api")

    assert report.healthy is False
    assert "无法解析服务域名" in report.conclusion
    assert "DNS 解析" in report.to_text()


def test_write_diagnostic_report_saves_text(tmp_path: Path, monkeypatch):
    def fake_getaddrinfo(host, port, type):
        raise socket.gaierror("nodename nor servname provided")

    class Client:
        def __init__(self, timeout, follow_redirects):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url):
            raise httpx.ConnectError("nodename nor servname provided")

    monkeypatch.setattr("aidrama_desktop.api.diagnostics.socket.getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr("aidrama_desktop.api.diagnostics.httpx.Client", Client)

    report = diagnose_server("https://ad.ai-drama.uk/api")
    report_path = write_diagnostic_report(report, tmp_path / "work")

    assert report_path.name == "network-diagnostics.txt"
    assert "AI Drama Desktop 网络诊断报告" in report_path.read_text(encoding="utf-8")
