from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic
from urllib.parse import urlencode, urlparse

import httpx

from aidrama_desktop.api.client import normalize_base_url

DIAGNOSTIC_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str
    elapsed_ms: int | None = None

    def as_line(self) -> str:
        mark = "OK" if self.ok else "FAIL"
        elapsed = f" ({self.elapsed_ms}ms)" if self.elapsed_ms is not None else ""
        return f"[{mark}] {self.name}{elapsed}: {self.detail}"


@dataclass(frozen=True)
class NetworkDiagnosticReport:
    server_url: str
    host: str
    port: int
    generated_at: datetime
    probes: tuple[ProbeResult, ...]

    @property
    def healthy(self) -> bool:
        return any(probe.name.startswith("HTTP") and probe.ok for probe in self.probes)

    @property
    def conclusion(self) -> str:
        if self.healthy:
            return "服务地址可以连通；如果仍然登录失败，优先检查用户名、密码、账号状态或设备绑定。"
        failed_names = {probe.name for probe in self.probes if not probe.ok}
        if "DNS 解析" in failed_names:
            return "当前网络无法解析服务域名，常见原因是 DNS、运营商解析或代理路由问题。"
        if any(name.startswith("TCP") for name in failed_names):
            return "域名能解析，但当前网络无法建立连接，常见原因是路由、防火墙或运营商到该节点不通。"
        return "当前网络无法完成服务探测，请把报告发给管理员继续排查。"

    def to_text(self) -> str:
        lines = [
            "AI Drama Desktop 网络诊断报告",
            f"生成时间：{self.generated_at.isoformat(timespec='seconds')}",
            f"服务地址：{self.server_url}",
            f"服务主机：{self.host}:{self.port}",
            "",
            "探测结果：",
            *[probe.as_line() for probe in self.probes],
            "",
            f"结论：{self.conclusion}",
        ]
        return "\n".join(lines)


def diagnose_server(server_url: str) -> NetworkDiagnosticReport:
    base_url = normalize_base_url(server_url)
    parsed = urlparse(base_url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    probes: list[ProbeResult] = []

    addresses = _resolve_host(host, port, probes)
    if addresses:
        _probe_tcp(port, addresses, probes)
    else:
        probes.append(ProbeResult("TCP 连接", False, "DNS 解析失败，跳过 TCP 连接。"))
    _probe_http(base_url, probes)

    return NetworkDiagnosticReport(
        server_url=base_url,
        host=host or "-",
        port=port,
        generated_at=datetime.now(),
        probes=tuple(probes),
    )


def write_diagnostic_report(report: NetworkDiagnosticReport, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    report_path = work_dir / "network-diagnostics.txt"
    report_path.write_text(report.to_text(), encoding="utf-8")
    return report_path


def _resolve_host(host: str, port: int, probes: list[ProbeResult]) -> list[str]:
    if not host:
        probes.append(ProbeResult("DNS 解析", False, "服务地址缺少主机名。"))
        return []
    started = monotonic()
    try:
        info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exception:
        probes.append(ProbeResult("DNS 解析", False, _short_error(exception), _elapsed_ms(started)))
        return []
    addresses = sorted({item[4][0] for item in info if item[4]})
    detail = ", ".join(addresses[:8]) if addresses else "没有返回可用 IP。"
    probes.append(ProbeResult("DNS 解析", bool(addresses), detail, _elapsed_ms(started)))
    return addresses


def _probe_tcp(port: int, addresses: list[str], probes: list[ProbeResult]) -> None:
    targets = addresses[:3]
    for target in targets:
        started = monotonic()
        try:
            with socket.create_connection((target, port), timeout=DIAGNOSTIC_TIMEOUT_SECONDS):
                probes.append(ProbeResult(f"TCP 连接 {target}:{port}", True, "连接成功。", _elapsed_ms(started)))
                return
        except OSError as exception:
            probes.append(
                ProbeResult(
                    f"TCP 连接 {target}:{port}",
                    False,
                    _short_error(exception),
                    _elapsed_ms(started),
                )
            )


def _probe_http(base_url: str, probes: list[ProbeResult]) -> None:
    query = urlencode({"platform": "MAC", "currentVersion": "diagnostic"})
    url = f"{base_url}/desktop/versions/check?{query}"
    started = monotonic()
    try:
        with httpx.Client(timeout=DIAGNOSTIC_TIMEOUT_SECONDS, follow_redirects=False) as client:
            response = client.get(url)
    except httpx.TimeoutException as exception:
        probes.append(ProbeResult("HTTP/API 探测", False, f"请求超时：{_short_error(exception)}", _elapsed_ms(started)))
        return
    except httpx.RequestError as exception:
        probes.append(ProbeResult("HTTP/API 探测", False, _short_error(exception), _elapsed_ms(started)))
        return

    headers = []
    server = response.headers.get("server")
    cf_ray = response.headers.get("cf-ray")
    trace_id = response.headers.get("x-trace-id")
    if server:
        headers.append(f"server={server}")
    if cf_ray:
        headers.append(f"cf-ray={cf_ray}")
    if trace_id:
        headers.append(f"x-trace-id={trace_id}")
    suffix = f"；{'，'.join(headers)}" if headers else ""
    ok = response.status_code < 500
    probes.append(
        ProbeResult(
            "HTTP/API 探测",
            ok,
            f"HTTP {response.status_code}{suffix}",
            _elapsed_ms(started),
        )
    )


def _elapsed_ms(started: float) -> int:
    return round((monotonic() - started) * 1000)


def _short_error(exception: BaseException) -> str:
    message = str(exception).strip()
    return message or exception.__class__.__name__
