#!/usr/bin/env python3
"""Minimal stdio MCP bridge for DeepSeek's Search and Fetch REST APIs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SEARCH_ENDPOINT = "https://api.deepseek.com/v1/tools/search"
FETCH_ENDPOINT = "https://api.deepseek.com/v1/tools/fetch"
DEFAULT_TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
API_KEY_FILE = Path(__file__).resolve().parents[1] / "tmp" / "deepseek-web" / "api-key.dpapi"
PROTOCOL_VERSION = "2024-11-05"


class ToolError(Exception):
    """An expected, safe-to-report tool failure."""


def _read_dpapi_key(path: Path = API_KEY_FILE) -> str | None:
    """Decrypt a ConvertFrom-SecureString file without exposing it to logs."""
    if os.name != "nt" or not path.is_file():
        return None
    try:
        # Use Windows DPAPI directly: child PowerShell may inherit a module path
        # from a bundled runtime that cannot load Windows PowerShell modules.
        import ctypes
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

        raw = bytes.fromhex(path.read_text(encoding="ascii").strip())
        buffer = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
        encrypted = Blob(len(raw), buffer)
        decrypted = Blob()
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        crypt.CryptUnprotectData.restype = wintypes.BOOL
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree.restype = ctypes.c_void_p
        if not crypt.CryptUnprotectData(ctypes.byref(encrypted), None, None, None, None, 1, ctypes.byref(decrypted)):
            return None
        try:
            key = ctypes.string_at(decrypted.data, decrypted.size).decode("utf-16-le").strip()
            return key or None
        finally:
            ctypes.memset(decrypted.data, 0, decrypted.size)
            kernel.LocalFree(decrypted.data)
    except (OSError, ValueError, UnicodeError):
        return None


def get_api_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    return key or _read_dpapi_key()


def _validate_query(query: Any, count: Any, need_content: Any) -> None:
    if not isinstance(query, str) or not 1 <= len(query) <= 128 or not query.strip():
        raise ToolError("Invalid query: expected 1–128 non-whitespace characters.")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 50:
        raise ToolError("Invalid count: expected an integer from 1 to 50.")
    if not isinstance(need_content, bool):
        raise ToolError("Invalid need_content: expected a boolean.")


def _validate_url(url: Any) -> None:
    if not isinstance(url, str) or not 1 <= len(url) <= 8192:
        raise ToolError("Invalid URL: expected an HTTP(S) URL up to 8192 characters.")
    try:
        parsed = urllib.parse.urlsplit(url)
        valid = parsed.scheme.lower() in ("http", "https") and bool(parsed.hostname)
        valid = valid and parsed.username is None and parsed.password is None
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            valid = False
    except (ValueError, UnicodeError):
        valid = False
    if not valid:
        raise ToolError("Invalid URL: expected HTTP(S), a host, and no embedded credentials.")


def _post_json(endpoint: str, payload: dict[str, Any], *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    key = get_api_key()
    if not key:
        raise ToolError("DeepSeek API key unavailable.")
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ToolError("DeepSeek API response exceeded the size limit.")
    except urllib.error.HTTPError as exc:
        # Do not read or forward the response body: it may contain sensitive data.
        raise ToolError(f"DeepSeek API returned HTTP {exc.code}.") from None
    except (TimeoutError, urllib.error.URLError, OSError) as exc:
        if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError):
            raise ToolError("DeepSeek API request timed out.") from None
        if isinstance(exc, TimeoutError):
            raise ToolError("DeepSeek API request timed out.") from None
        raise ToolError("DeepSeek API connection failed.") from None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ToolError("DeepSeek API returned an invalid JSON response.") from None


def deepseek_search(query: str, count: int = 5, need_content: bool = True) -> Any:
    _validate_query(query, count, need_content)
    return _post_json(SEARCH_ENDPOINT, {"query": query, "count": count, "need_content": need_content})


def deepseek_fetch(url: str) -> Any:
    _validate_url(url)
    return _post_json(FETCH_ENDPOINT, {"url": url})


TOOLS = [
    {
        "name": "deepseek_search",
        "description": "Search the public web using DeepSeek Search API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 128},
                "count": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
                "need_content": {"type": "boolean", "default": True},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "deepseek_fetch",
        "description": "Fetch a public HTTP(S) page using DeepSeek Fetch API.",
        "inputSchema": {
            "type": "object",
            "properties": {"url": {"type": "string", "minLength": 1, "maxLength": 8192, "format": "uri"}},
            "required": ["url"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
]


def _rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_rpc(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _rpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
    method = message["method"]
    request_id = message.get("id")
    is_notification = "id" not in message
    params = message.get("params", {})
    if not isinstance(params, dict):
        return None if is_notification else _rpc_error(request_id, -32602, "Invalid params")

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "deepseek-web", "version": "1.0.0"},
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            result = {"content": [{"type": "text", "text": "Tool arguments must be an object."}], "isError": True}
        else:
            try:
                if name == "deepseek_search":
                    value = deepseek_search(
                        arguments.get("query"),
                        arguments.get("count", 5),
                        arguments.get("need_content", True),
                    )
                elif name == "deepseek_fetch":
                    value = deepseek_fetch(arguments.get("url"))
                else:
                    raise ToolError("Unknown tool.")
                result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "isError": False}
            except ToolError as exc:
                result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
            except Exception:
                # Keep exception details (which can contain headers or key material) off stdio.
                result = {"content": [{"type": "text", "text": "Tool execution failed."}], "isError": True}
    else:
        if is_notification:
            return None
        return _rpc_error(request_id, -32601, "Method not found")

    return None if is_notification else {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_stdio() -> int:
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        try:
            message = json.loads(line.decode("utf-8"))
            response = handle_rpc(message)
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = _rpc_error(None, -32700, "Parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DeepSeek Search/Fetch MCP stdio bridge")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Report local configuration without network access")
    group.add_argument("--search", metavar="QUERY", help="Run Search API and print JSON")
    group.add_argument("--fetch", metavar="URL", help="Run Fetch API and print JSON")
    args = parser.parse_args(argv)
    if args.check:
        print(json.dumps({"key_available": bool(get_api_key()), "search_endpoint": SEARCH_ENDPOINT, "fetch_endpoint": FETCH_ENDPOINT}, ensure_ascii=False))
        return 0
    if args.search is not None or args.fetch is not None:
        try:
            result = deepseek_search(args.search) if args.search is not None else deepseek_fetch(args.fetch)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        except ToolError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 1
        except Exception:
            print(json.dumps({"error": "Tool execution failed."}, ensure_ascii=False))
            return 1
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
