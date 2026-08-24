"""Minimal Model Context Protocol client for the Grafana MCP server.

CUTSCOPE's telemetry loop is deliberately split across two protocols:

  WRITE path : cutscope/telemetry.py pushes metrics and spans to Grafana Cloud
               over OTLP (opentelemetry-exporter-otlp-proto-http).
  READ  path : this module. Every metric the Gemini decision agent is shown is
               fetched back out of Grafana by calling a tool on the Grafana MCP
               server (github.com/grafana/mcp-grafana, or the hosted Grafana
               Cloud MCP endpoint at https://mcp.grafana.com/mcp).

Write via OTLP, read via MCP. The direct Prometheus HTTP query kept in
grafana_query.py is a documented fallback for when MCP is unreachable, never
the primary path.

Transport is Streamable HTTP per the MCP spec (2025-06-18): every JSON-RPC
message is its own HTTP POST, and the server may answer with either
application/json or a text/event-stream SSE body. Both are handled here.

Dependencies: Python standard library only. No MCP SDK, no third-party HTTP
client -- the hackathon rules forbid non-Google AI vendors at runtime, and the
smallest way to guarantee nothing forbidden is pulled in transitively is to add
no dependency at all.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .errors import CutscopeError

# The spec revision this client implements and advertises.
PROTOCOL_VERSION = "2025-06-18"

# Grafana's fully hosted MCP server. The open source server (run as a sidecar or
# in the same container) is the other supported target; see
# docs/GRAFANA_MCP_SETUP.md for both.
HOSTED_GRAFANA_MCP_URL = "https://mcp.grafana.com/mcp"


class GrafanaMcpUnavailable(CutscopeError):
    """The Grafana MCP server could not be reached, authorised, or understood."""


@dataclass(frozen=True)
class McpConfig:
    """Where the Grafana MCP server lives and how to authenticate to it."""

    url: str
    token: str = ""
    # Only meaningful for the hosted endpoint, which multiplexes across stacks.
    grafana_url: str = ""
    timeout_seconds: float = 20.0

    @classmethod
    def from_environment(cls) -> "McpConfig | None":
        """Return None when MCP is not configured, so the caller can fall back."""
        url = os.environ.get("GRAFANA_MCP_URL", "").strip()
        token = os.environ.get("GRAFANA_MCP_TOKEN", "").strip()
        grafana_url = os.environ.get("GRAFANA_URL", "").strip()
        if not url and token:
            # A token alone is enough to mean "use Grafana's hosted MCP server".
            url = HOSTED_GRAFANA_MCP_URL
        if not url:
            return None
        return cls(
            url=url,
            token=token,
            grafana_url=grafana_url,
            timeout_seconds=_positive_float("GRAFANA_MCP_TIMEOUT_SECONDS", 20.0),
        )


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass
class McpToolResult:
    """A tools/call result, already unwrapped from MCP's content envelope."""

    tool: str
    payload: Any
    is_error: bool = False
    raw_text: str = ""


class McpClient:
    """JSON-RPC over MCP Streamable HTTP. connect / list_tools / call_tool."""

    def __init__(self, config: McpConfig) -> None:
        self._config = config
        self._session_id: str | None = None
        self._negotiated_version: str | None = None
        self._next_id = 0
        self.server_info: dict[str, Any] = {}

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> dict[str, Any]:
        """Perform the MCP initialize handshake. Safe to call more than once."""
        if self._negotiated_version:
            return self.server_info
        result = self._request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "cutscope", "version": "0.1.0"},
            },
            expect_session=True,
        )
        self._negotiated_version = str(result.get("protocolVersion") or PROTOCOL_VERSION)
        self.server_info = dict(result.get("serverInfo") or {})
        # The spec requires this notification before any other request.
        self._notify("notifications/initialized")
        return self.server_info

    def close(self) -> None:
        """Best-effort session teardown; servers may refuse with 405."""
        if not self._session_id:
            return
        request = Request(self._config.url, method="DELETE", headers=self._headers())
        try:
            with urlopen(request, timeout=self._config.timeout_seconds):  # noqa: S310
                pass
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        finally:
            self._session_id = None

    def __enter__(self) -> "McpClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- tools --------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        self.connect()
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self._request("tools/list", params)
            tools.extend(result.get("tools") or [])
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> McpToolResult:
        self.connect()
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        text = "\n".join(
            block.get("text", "")
            for block in (result.get("content") or [])
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
        is_error = bool(result.get("isError"))
        # Prefer the typed result when the server sends one; otherwise the text
        # block is nearly always JSON for Grafana's query tools.
        if "structuredContent" in result and result["structuredContent"] is not None:
            payload: Any = result["structuredContent"]
        else:
            try:
                payload = json.loads(text) if text else None
            except json.JSONDecodeError:
                payload = text or None
        if is_error:
            raise GrafanaMcpUnavailable(
                f"Grafana MCP tool {name!r} returned an error: {_clip(text or 'no detail supplied')}"
            )
        return McpToolResult(tool=name, payload=payload, is_error=is_error, raw_text=text)

    # -- JSON-RPC plumbing --------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            # The spec requires the client to accept both response shapes.
            "Accept": "application/json, text/event-stream",
        }
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"
        if self._config.grafana_url:
            headers["X-Grafana-URL"] = self._config.grafana_url
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        if self._negotiated_version:
            headers["MCP-Protocol-Version"] = self._negotiated_version
        return headers

    def _request(
        self, method: str, params: dict[str, Any], *, expect_session: bool = False
    ) -> dict[str, Any]:
        self._next_id += 1
        message_id = self._next_id
        body = {"jsonrpc": "2.0", "id": message_id, "method": method, "params": params}
        status, headers, raw = self._post(body, method)
        if expect_session:
            session = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
            if session:
                self._session_id = session
        message = _select_response(raw, headers.get("Content-Type", ""), message_id, method)
        if "error" in message:
            error = message["error"] or {}
            raise GrafanaMcpUnavailable(
                f"Grafana MCP rejected {method!r}: "
                f"{error.get('message', 'unknown error')} (code {error.get('code', 'n/a')})"
            )
        result = message.get("result")
        if not isinstance(result, dict):
            raise GrafanaMcpUnavailable(f"Grafana MCP returned no result object for {method!r}.")
        return result

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params or {}}, method)

    def _post(self, body: dict[str, Any], method: str) -> tuple[int, dict[str, str], bytes]:
        request = Request(
            self._config.url,
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        try:
            # noqa: S310 - the URL is an operator-supplied environment variable.
            with urlopen(request, timeout=self._config.timeout_seconds) as response:  # noqa: S310
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as exc:
            detail = _clip(exc.read().decode("utf-8", "replace"))
            raise GrafanaMcpUnavailable(_http_hint(exc.code, method, self._config, detail)) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise GrafanaMcpUnavailable(
                f"Grafana MCP server at {self._config.url} is unreachable while calling "
                f"{method!r}: {_clip(str(exc))}"
            ) from exc


def _select_response(raw: bytes, content_type: str, message_id: int, method: str) -> dict[str, Any]:
    """Pull the JSON-RPC response for message_id out of a JSON or SSE body."""
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        raise GrafanaMcpUnavailable(f"Grafana MCP returned an empty body for {method!r}.")
    if "text/event-stream" in content_type.lower():
        for message in _iter_sse_messages(text):
            # Notifications and server-initiated requests may precede the answer.
            if message.get("id") == message_id:
                return message
        raise GrafanaMcpUnavailable(
            f"Grafana MCP SSE stream for {method!r} closed without a response."
        )
    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GrafanaMcpUnavailable(
            f"Grafana MCP returned a non-JSON body for {method!r}: {_clip(text)}"
        ) from exc
    if isinstance(message, list):
        for item in message:
            if isinstance(item, dict) and item.get("id") == message_id:
                return item
        raise GrafanaMcpUnavailable(f"Grafana MCP batch response held no answer for {method!r}.")
    if not isinstance(message, dict):
        raise GrafanaMcpUnavailable(f"Grafana MCP returned an unexpected body for {method!r}.")
    if message.get("id") != message_id:
        # JSON-RPC allows a null id only on an error the server could not attribute
        # to a request; surface that error rather than masking it as a mismatch.
        if message.get("id") is None and "error" in message:
            return message
        raise GrafanaMcpUnavailable(
            f"Grafana MCP answered {method!r} with id {message.get('id')!r}, expected {message_id!r}."
        )
    return message


def _iter_sse_messages(text: str) -> Iterator[dict[str, Any]]:
    """Yield JSON payloads from SSE `data:` lines, per the SSE framing rules."""
    data_lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.startswith(":"):
            continue  # comment / keep-alive
        if line == "":
            payload = "\n".join(data_lines).strip()
            data_lines = []
            if payload:
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    yield parsed
            continue
        field_name, _, value = line.partition(":")
        if field_name == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)
    payload = "\n".join(data_lines).strip()
    if payload:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(parsed, dict):
            yield parsed


def _http_hint(code: int, method: str, config: McpConfig, detail: str) -> str:
    """Turn an HTTP failure into something a human can act on immediately."""
    where = f"{config.url} (calling {method!r})"
    if code in (401, 403):
        return (
            f"Grafana MCP refused the credential at {where} with HTTP {code}. "
            "GRAFANA_MCP_TOKEN must be a token that can READ metrics -- an OTLP "
            "push token (scope 'otlp:write') is not accepted here. Use a Grafana "
            "service account token with the Viewer role and the "
            "'datasources:query' permission against the open source mcp-grafana "
            "server, or an OAuth access token for the hosted endpoint. "
            f"See docs/GRAFANA_MCP_SETUP.md. Server said: {detail}"
        )
    if code == 404 and config.url.rstrip("/").endswith("/mcp"):
        return (
            f"Grafana MCP returned HTTP 404 at {where}. Either the session expired "
            "or the endpoint path is wrong; the Streamable HTTP path is '/mcp'. "
            f"Server said: {detail}"
        )
    if code == 503:
        return (
            f"Grafana returned HTTP 503 at {where}. A Grafana Cloud free stack that "
            "has been idle is suspended and must be woken by signing in at the stack "
            f"URL once in a browser. Server said: {detail}"
        )
    return f"Grafana MCP call failed at {where} with HTTP {code}: {detail}"


def _clip(text: str, limit: int = 300) -> str:
    flat = " ".join(text.split())
    return flat[:limit] if flat else "(no detail)"


# ---------------------------------------------------------------------------
# Self-check. `python -m cutscope.mcp_grafana` runs offline assertions;
# `python -m cutscope.mcp_grafana --probe` talks to the configured MCP server
# and prints the tools it exposes, which is also the fastest way for a human to
# confirm their token works.
# ---------------------------------------------------------------------------


def _selfcheck() -> None:
    sse = (
        ": keep-alive\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n'
        "\n"
        "event: message\n"
        'data: {"jsonrpc":"2.0","id":7,"result":{"tools":[]}}\n'
        "\n"
    )
    messages = list(_iter_sse_messages(sse))
    assert len(messages) == 2, messages
    picked = _select_response(sse.encode(), "text/event-stream", 7, "tools/list")
    assert picked["result"] == {"tools": []}, picked

    # A response split across multiple data: lines must be rejoined, not dropped.
    split = 'event: message\ndata: {"jsonrpc":"2.0","id":1,\ndata: "result":{"ok":true}}\n\n'
    assert _select_response(split.encode(), "text/event-stream", 1, "x")["result"] == {"ok": True}

    plain = b'{"jsonrpc":"2.0","id":3,"result":{"ok":true}}'
    assert _select_response(plain, "application/json", 3, "x")["result"] == {"ok": True}

    # An id that never arrives must raise, never silently return the wrong message.
    for bad, ctype in ((sse.encode(), "text/event-stream"), (plain, "application/json")):
        try:
            _select_response(bad, ctype, 999, "x")
        except GrafanaMcpUnavailable:
            pass
        else:
            raise AssertionError("mismatched JSON-RPC id was not rejected")

    # A 401 must name the scope the operator actually needs.
    hint = _http_hint(401, "tools/call", McpConfig(url=HOSTED_GRAFANA_MCP_URL), "nope")
    assert "otlp:write" in hint and "GRAFANA_MCP_TOKEN" in hint, hint

    assert McpConfig.from_environment.__doc__
    print("mcp_grafana selfcheck: ok")


def _probe() -> None:
    config = McpConfig.from_environment()
    if config is None:
        print("GRAFANA_MCP_URL / GRAFANA_MCP_TOKEN are unset; see docs/GRAFANA_MCP_SETUP.md")
        raise SystemExit(2)
    print(f"connecting to {config.url}")
    with McpClient(config) as client:
        print(f"server: {client.server_info}")
        tools = client.list_tools()
        print(f"{len(tools)} tools exposed")
        for tool in tools:
            if "prometheus" in tool.get("name", "") or tool.get("name") == "list_datasources":
                print(f"  {tool['name']}: {json.dumps(tool.get('inputSchema', {}))[:400]}")


if __name__ == "__main__":  # pragma: no cover
    import sys
    from pathlib import Path

    from .config import load_dotenv

    load_dotenv(Path.cwd() / ".env")
    if "--probe" in sys.argv:
        _probe()
    else:
        _selfcheck()
