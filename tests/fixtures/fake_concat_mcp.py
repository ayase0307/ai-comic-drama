# -*- coding: utf-8 -*-
"""測試用的假 Concat headless MCP（stdio JSON-RPC）：media_import 回 createdId，explode 回錯誤。"""
import json
import sys

for raw in sys.stdin:
    msg = json.loads(raw)
    if "id" not in msg:
        continue
    ident = msg["id"]
    if msg.get("method") == "initialize":
        result = {"protocolVersion": "2025-06-18", "capabilities": {}, "serverInfo": {"name": "fake-concat"}}
    elif msg.get("method") == "tools/call":
        name = msg["params"]["name"]
        if name == "explode":
            result = {"isError": True, "content": [{"type": "text", "text": "boom"}]}
        else:
            result = {"structuredContent": {"createdId": f"id-{ident}", "tool": name}}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": ident, "result": result}) + "\n")
    sys.stdout.flush()
