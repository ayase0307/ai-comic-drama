import importlib.util
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deepseek_web_mcp.py"
SPEC = importlib.util.spec_from_file_location("deepseek_web_mcp", SCRIPT)
deepseek = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(deepseek)


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.body


class DeepSeekWebTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-secret-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    @mock.patch.object(deepseek.urllib.request, "urlopen")
    def test_search_posts_expected_json_and_auth(self, urlopen):
        urlopen.return_value = FakeResponse(b'{"results":[{"title":"ok"}]}')
        result = deepseek.deepseek_search("hello", count=3, need_content=False)
        self.assertEqual(result, {"results": [{"title": "ok"}]})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, deepseek.SEARCH_ENDPOINT)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-secret-key")
        self.assertEqual(json.loads(request.data), {"query": "hello", "count": 3, "need_content": False})

    @mock.patch.object(deepseek.urllib.request, "urlopen")
    def test_fetch_posts_url(self, urlopen):
        urlopen.return_value = FakeResponse(b'{"title":"page","content":"text"}')
        self.assertEqual(deepseek.deepseek_fetch("https://example.org/a"), {"title": "page", "content": "text"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, deepseek.FETCH_ENDPOINT)
        self.assertEqual(json.loads(request.data), {"url": "https://example.org/a"})

    def test_validators_reject_bad_inputs(self):
        for query in ("", "   ", "x" * 129, None):
            with self.subTest(query=query), self.assertRaises(deepseek.ToolError):
                deepseek.deepseek_search(query)
        for count in (True, 0, 51, 2.0, "2"):
            with self.subTest(count=count), self.assertRaises(deepseek.ToolError):
                deepseek.deepseek_search("ok", count=count)
        for need_content in (1, "true", None):
            with self.subTest(need_content=need_content), self.assertRaises(deepseek.ToolError):
                deepseek.deepseek_search("ok", need_content=need_content)
        for url in ("file:///etc/passwd", "https:///missing-host", "https://user:pw@example.org", "ftp://example.org"):
            with self.subTest(url=url), self.assertRaises(deepseek.ToolError):
                deepseek.deepseek_fetch(url)

    @mock.patch.object(deepseek.urllib.request, "urlopen")
    def test_http_error_never_leaks_server_body_or_key(self, urlopen):
        urlopen.side_effect = deepseek.urllib.error.HTTPError(
            deepseek.SEARCH_ENDPOINT, 401, "unauthorized", {}, io.BytesIO(b"test-secret-key leaked body")
        )
        with self.assertRaisesRegex(deepseek.ToolError, "HTTP 401") as captured:
            deepseek.deepseek_search("hello")
        self.assertNotIn("test-secret-key", str(captured.exception))
        self.assertNotIn("leaked body", str(captured.exception))

    def test_mcp_initialize_ping_and_tools_list(self):
        init = deepseek.handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": deepseek.PROTOCOL_VERSION}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "deepseek-web")
        self.assertIn("tools", init["result"]["capabilities"])
        ping = deepseek.handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "ping"})
        self.assertEqual(ping["result"], {})
        listed = deepseek.handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        self.assertEqual([t["name"] for t in listed["result"]["tools"]], ["deepseek_search", "deepseek_fetch"])
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in listed["result"]["tools"]))

    @mock.patch.object(deepseek, "deepseek_search", return_value={"results": []})
    def test_mcp_tool_call(self, search):
        result = deepseek.handle_rpc({
            "jsonrpc": "2.0", "id": "call-1", "method": "tools/call",
            "params": {"name": "deepseek_search", "arguments": {"query": "example"}},
        })
        search.assert_called_once_with("example", 5, True)
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(json.loads(result["result"]["content"][0]["text"]), {"results": []})


if __name__ == "__main__":
    unittest.main()
