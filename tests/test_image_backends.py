"""生圖工具偵測與使用者選擇（scripts/image_backends.py、h3d imagegen、h3d next／inbox 串接）。

規則：生圖後端由使用者選，不自行預設。偵測不生圖、不花錢、不連外部付費 API、不讀 token 值。
"""
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
for extra in (SCRIPTS, SCRIPTS / "review", SCRIPTS / "storyboard"):
    sys.path.insert(0, str(extra))

import decisions  # noqa: E402
import image_backends as ib  # noqa: E402
import inbox  # noqa: E402
import next_step  # noqa: E402
import project_state as ps  # noqa: E402


def row(bid, available, reason="r"):
    meta = ib.BACKENDS[bid]
    status = {True: "available", False: "unavailable", None: "unknown"}[available]
    return {"id": bid, "label": meta["label"], "stages": list(meta["stages"]), "selectable": meta["selectable"],
            "available": available, "status": status, "reason": reason}


def rows(**avail):
    """rows(codex=True, qwen=False) → 偵測結果；沒列的 manual 永遠可用。"""
    out = [row(b, a) for b, a in avail.items()]
    if "manual" not in avail:
        out.append(row("manual", True, "永遠可用"))
    return out


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()


class DetectTests(_Tmp):
    """偵測：mock PATH／CODEX_HOME／端點，不碰真實環境。"""

    def fake_codex(self):
        bindir = self.dir / "bin"
        bindir.mkdir()
        marker = self.dir / "codex-was-executed"
        exe = bindir / ("codex.exe" if sys.platform.startswith("win") else "codex")
        exe.write_text(f"#!/bin/sh\ntouch '{marker}'\n", encoding="utf-8")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        return bindir, marker

    def env(self, **extra):
        base = {"PATH": str(self.dir / "empty"), "HOME": str(self.dir / "home"),
                "FREEVIDEO_API_URL": "http://127.0.0.1:9", "COMFYUI_URL": "http://127.0.0.1:9"}
        base.update(extra)
        return base

    def by_id(self, result):
        return {r["id"]: r for r in result}

    def test_codex_on_path_and_logged_in_is_available_without_running_it(self):
        bindir, marker = self.fake_codex()
        home = self.dir / "codexhome"
        home.mkdir()
        (home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt",
                                                    "tokens": {"access_token": "SECRET-VALUE"}}), encoding="utf-8")
        got = self.by_id(ib.detect(env=self.env(PATH=str(bindir), CODEX_HOME=str(home)),
                                   probe=lambda h, p: False))
        self.assertTrue(got["codex"]["available"])
        self.assertIn("已登入", got["codex"]["reason"])
        self.assertNotIn("SECRET-VALUE", json.dumps(got, ensure_ascii=False), "不得讀出 token 值")
        self.assertFalse(marker.exists(), "偵測不得執行 codex（不生圖、不花錢）")

    def test_codex_not_logged_in_or_missing_is_unavailable_with_reason(self):
        bindir, _ = self.fake_codex()
        got = self.by_id(ib.detect(env=self.env(PATH=str(bindir), CODEX_HOME=str(self.dir / "nohome")),
                                   probe=lambda h, p: False))
        self.assertFalse(got["codex"]["available"])
        self.assertIn("找不到登入資料", got["codex"]["reason"])
        got = self.by_id(ib.detect(env=self.env(), probe=lambda h, p: False))
        self.assertFalse(got["codex"]["available"])
        self.assertIn("PATH 上找不到", got["codex"]["reason"])

    def test_qwen_needs_freevideo_endpoint_enabled(self):
        calls = []

        def probe(host, port):
            calls.append((host, port))
            return True

        got = self.by_id(ib.detect(env=self.env(FREEVIDEO_API_URL="http://10.0.0.5:8189/freevideo/agent/v1"),
                                   probe=probe, fetch=lambda url: {"enabled": True}))
        self.assertTrue(got["qwen"]["available"])
        self.assertIn(("10.0.0.5", 8189), calls, "照 FREEVIDEO_API_URL 探測")
        got = self.by_id(ib.detect(env=self.env(), probe=lambda h, p: True, fetch=lambda url: {"enabled": False}))
        self.assertFalse(got["qwen"]["available"])
        self.assertIn("未啟用", got["qwen"]["reason"])
        got = self.by_id(ib.detect(env=self.env(), probe=lambda h, p: False))
        self.assertFalse(got["qwen"]["available"])
        self.assertIn("連不上", got["qwen"]["reason"])

    def test_qwen_real_local_http_endpoint(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                body = json.dumps({"enabled": True}).encode()
                self.send_response(200 if self.path == "/freevideo/agent" else 404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            port = server.server_address[1]
            got = self.by_id(ib.detect(4, env=self.env(FREEVIDEO_API_URL=f"http://127.0.0.1:{port}")))
            self.assertTrue(got["qwen"]["available"], got["qwen"]["reason"])
        finally:
            server.shutdown()
            server.server_close()

    def test_grok_unknown_unless_agent_declares_and_manual_always(self):
        got = self.by_id(ib.detect(env=self.env(), probe=lambda h, p: False))
        self.assertIsNone(got["grok"]["available"])
        self.assertTrue(got["manual"]["available"])
        self.assertFalse(got["comfyui"]["selectable"])
        got = self.by_id(ib.detect(env=self.env(AICD_AGENT_IMAGE_TOOL="grok"), probe=lambda h, p: False))
        self.assertTrue(got["grok"]["available"])

    def test_stage_filter_and_commands(self):
        s2 = {r["id"] for r in ib.detect(2, env=self.env(), probe=lambda h, p: False)}
        s4 = {r["id"] for r in ib.detect(4, env=self.env(), probe=lambda h, p: False)}
        self.assertEqual(s2, {"codex", "grok", "manual"})
        self.assertEqual(s4, {"codex", "qwen", "manual"})
        self.assertIn('codex_storyboard_panels.py" --root . --episode EP03 --model <使用者指定模型>',
                      ib.command_for("codex", 4, "EP03"))
        self.assertIn('qwen_storyboard_grid.py" --layer2-dir layer2 --episode EP03', ib.command_for("qwen", 4, "EP03"))
        self.assertIn("run_codex_asset_gen.py", ib.command_for("codex", 2))
        self.assertIsNone(ib.command_for("manual", 4))


class ChoiceFlowTests(_Tmp):
    """未選→詢問、已選→指令、選了不可用→重問、單一可用仍詢問。"""

    def test_unchosen_asks_user_and_lists_unavailable_with_reason(self):
        step = ib.next_step(self.dir, 4, "EP01", rows=rows(codex=True, qwen=False))
        self.assertTrue(step["ask_user"])
        self.assertEqual(step["state"], "unchosen")
        self.assertIn("imagegen --set <codex|manual> --stage 4", step["command"])
        self.assertIn("<使用者原話>", step["command"])
        self.assertNotIn("codex_storyboard_panels", step["command"], "沒選就不給固定指令")
        self.assertIn("不可用：qwen", step["action"])
        self.assertIn("不要自己預設", step["action"])

    def test_single_available_generator_still_asks_and_marks_recommendation(self):
        step = ib.next_step(self.dir, 4, rows=rows(codex=True, qwen=False))
        self.assertTrue(step["ask_user"], "只有一個可用也要問")
        self.assertEqual(step["imagegen"]["recommended"], "codex")
        self.assertIn("建議", step["action"])
        both = ib.next_step(self.dir, 4, rows=rows(codex=True, qwen=True))
        self.assertTrue(both["ask_user"])
        self.assertIsNone(both["imagegen"]["recommended"], "兩個以上可用不替使用者建議")

    def test_chosen_gives_that_backend_command(self):
        decisions.decide(self.dir, "storyboard_engine", "qwen", "分鏡用 Qwen")
        step = ib.next_step(self.dir, 4, "EP02", rows=rows(codex=True, qwen=True))
        self.assertFalse(step["ask_user"])
        self.assertIn("qwen_storyboard_grid.py", step["command"])
        self.assertIn("--episode EP02", step["command"])

    def test_chosen_but_unavailable_warns_and_reasks(self):
        decisions.decide(self.dir, "storyboard_engine", "qwen", "分鏡用 Qwen")
        step = ib.next_step(self.dir, 4, rows=rows(codex=True, qwen=False))
        self.assertTrue(step["ask_user"])
        self.assertEqual(step["state"], "unavailable")
        self.assertIn("現在不可用", step["blocked"])
        self.assertIn("⚠️", step["action"])
        self.assertIn("imagegen --set", step["command"])

    def test_invalid_value_reasks(self):
        decisions.decide(self.dir, "design_engine", "midjourney", "用 MJ")
        res = ib.resolve(self.dir, 2, rows(codex=True))
        self.assertEqual(res["state"], "invalid")
        self.assertTrue(ib.next_step(self.dir, 2, rows=rows(codex=True))["ask_user"])

    def test_legacy_alias_value_is_understood(self):
        decisions.decide(self.dir, "design_engine", "codex_cli", "用 codex")
        self.assertEqual(ib.resolve(self.dir, 2, rows(codex=True))["backend"], "codex")


class SetBackendTests(_Tmp):
    def test_set_writes_shared_or_per_stage_decisions(self):
        ib.set_backend(self.dir, "codex", "設定圖和分鏡都用 Codex", rows=rows(codex=True))
        data = decisions.load(self.dir)
        self.assertEqual(decisions.get(data, "design_engine")["value"], "codex")
        self.assertEqual(decisions.get(data, "storyboard_engine")["value"], "codex")
        self.assertEqual(decisions.get(data, "storyboard_engine")["source"]["quote"], "設定圖和分鏡都用 Codex")
        ib.set_backend(self.dir, "qwen", "分鏡改 Qwen", rows=rows(qwen=True))
        data = decisions.load(self.dir)
        self.assertEqual(decisions.get(data, "storyboard_engine")["value"], "qwen")
        self.assertEqual(decisions.get(data, "design_engine")["value"], "codex", "qwen 只支援階段 4")

    def test_set_refuses_unsupported_unavailable_unselectable_and_missing_quote(self):
        with self.assertRaises(ib.ImagegenError):
            ib.set_backend(self.dir, "qwen", "x", stage="2", rows=rows(qwen=True))
        with self.assertRaises(ib.ImagegenError):
            ib.set_backend(self.dir, "codex", "x", rows=rows(codex=False))
        ib.set_backend(self.dir, "codex", "先定下來，回家機再跑", rows=rows(codex=False), allow_unavailable=True)
        with self.assertRaises(ib.ImagegenError):
            ib.set_backend(self.dir, "comfyui", "x", rows=rows())
        with self.assertRaises(ib.ImagegenError):
            ib.set_backend(self.dir, "nope", "x", rows=rows())
        with self.assertRaises(decisions.DecisionError):
            ib.set_backend(self.dir, "manual", "", rows=rows())

    def test_cli_set_and_detect(self):
        import contextlib
        import io
        with mock.patch.object(ib, "detect", return_value=rows(codex=True, qwen=False)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = ib.main(["--set", "manual", "--stage", "4", "--quote", "分鏡我自己手繪", "--root", str(self.dir)])
            self.assertEqual(code, 0)
            self.assertIn("storyboard_engine", out.getvalue())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ib.main(["--detect", "--json", "--root", str(self.dir)])
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["choices"]["4"]["backend"], "manual")
            self.assertEqual(payload["choices"]["2"]["state"], "unchosen")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                self.assertEqual(ib.main(["--set", "codex", "--root", str(self.dir)]), 2)
            self.assertIn("--quote", err.getvalue())

    def test_h3d_routes_imagegen(self):
        import h3d
        self.assertEqual(h3d.MODULE_FOR["imagegen"], "image_backends")
        with mock.patch.object(ib, "detect", return_value=rows(codex=True)), \
             mock.patch("sys.stdout"):
            self.assertEqual(h3d.main(["imagegen", "--detect"]), 0)


class NextAndInboxIntegrationTests(_Tmp):
    """h3d next／inbox：階段 2 缺設定圖工具、階段 4 缺構圖時的行為。"""

    def setUp(self):
        super().setUp()
        for folder in ("review", "images", "panels", "layer2"):
            (self.dir / folder).mkdir()

    def set_stage(self, cur):
        state = ps.load_state(self.dir)
        for i in range(8):
            key = ps.stage_key(i)
            state["stages"][key]["status"] = "approved" if i < cur else ("locked" if i > cur else "in_progress")
            if i < cur:
                state["stages"][key]["approval_snapshot"] = {"files": {}}
                state["stages"][key]["approval_dependencies"] = {"stage-0": "x"}
        ps.save_state(self.dir, state)

    def base_decisions(self, design_engine=True):
        for did, value in (("style", "半寫實"), ("aspect_ratio", "16:9"), ("dialogue_policy", "②")):
            decisions.decide(self.dir, did, value, "定了")
        if design_engine:
            decisions.decide(self.dir, "design_engine", "codex", "設定圖用 codex")

    def stage4_project(self):
        self.base_decisions()
        (self.dir / "layer2" / "layer2-EP01-S01-a.json").write_text(json.dumps(
            {"segment_id": "EP01-S01-a", "shots": [{"shot_id": "SH01"}]}), encoding="utf-8")
        self.set_stage(4)

    def test_next_stage4_unchosen_asks_instead_of_fixed_command(self):
        self.stage4_project()
        with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=True, qwen=False)):
            with mock.patch.object(next_step.ps, "first_unapproved", return_value=(4, None)):
                res = next_step.plan(self.dir)
        self.assertEqual(res["stage"], 4)
        self.assertIn("imagegen --set <codex|manual> --stage 4", res["next_command"])
        self.assertTrue(any("尚未選擇" in b for b in res["blocked_on"]), res["blocked_on"])
        self.assertEqual(res["imagegen"]["state"], "unchosen")

    def test_next_stage4_chosen_and_unavailable(self):
        self.stage4_project()
        decisions.decide(self.dir, "storyboard_engine", "codex", "分鏡用 Codex")
        with mock.patch.object(next_step.ps, "first_unapproved", return_value=(4, None)):
            with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=True)):
                res = next_step.plan(self.dir)
            self.assertIn('codex_storyboard_panels.py" --root . --episode EP01 --model', res["next_command"])
            with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=False)):
                res = next_step.plan(self.dir)
        self.assertIn("imagegen --set", res["next_command"])
        self.assertTrue(any("現在不可用" in b for b in res["blocked_on"]))

    def test_next_stage2_design_engine_missing_asks_with_detection(self):
        self.base_decisions(design_engine=False)
        self.set_stage(2)
        with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=True, grok=None)):
            with mock.patch.object(next_step.ps, "first_unapproved", return_value=(2, None)):
                res = next_step.plan(self.dir)
        self.assertIn("imagegen --set <codex|grok|manual> --stage 2", res["next_command"])
        self.assertIn("狀態未知需確認", res["action"])

    def test_next_stage2_missing_sheets_uses_chosen_engine_or_reasks(self):
        self.base_decisions()  # design_engine=codex
        (self.dir / "assets.md").write_text("### C-a　阿甲\n- **設定圖**：`images/c-a-sheet.png`\n", encoding="utf-8")
        self.set_stage(2)
        with mock.patch.object(next_step.ps, "first_unapproved", return_value=(2, None)):
            with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=True)):
                res = next_step.plan(self.dir)
            self.assertIn("run_codex_asset_gen.py", res["next_command"] or "", res)
            with mock.patch.object(next_step.image_backends, "detect", return_value=rows(codex=False)):
                res = next_step.plan(self.dir)
        self.assertIn("imagegen --set <manual> --stage 2", res["next_command"])
        self.assertTrue(any("現在不可用" in b for b in res["blocked_on"]))

    def test_next_stage2_no_image_scope_skips_engine_question(self):
        self.base_decisions(design_engine=False)
        decisions.decide(self.dir, "delivery_scope", '{"no_image": true}', "不用生圖")
        self.set_stage(2)
        with mock.patch.object(next_step.ps, "first_unapproved", return_value=(2, None)):
            res = next_step.plan(self.dir)
        self.assertNotIn("imagegen --set", res["next_command"] or "")

    def test_inbox_stage4_card_greys_out_unavailable(self):
        self.stage4_project()
        with mock.patch.object(inbox.image_backends, "detect", return_value=rows(codex=True, qwen=False)):
            card = inbox.imagegen_card_if_needed(self.dir, 4)
        self.assertEqual(card["id"], "D4-imagegen-backend")
        self.assertEqual(card["options"][0]["label"], "Codex", "只有一個可用：放第一個並標建議")
        self.assertFalse(card["no_recommendation"])
        self.assertEqual([o["label"] for o in card["unavailable_options"]], ["Qwen-Image"])
        self.assertTrue(card["unavailable_options"][0]["reason"], "灰掉的選項要寫原因")
        problems = []
        norm = inbox._normalize_card(card, problems)
        self.assertEqual(problems, [])
        html = inbox.inbox_page.card_html(norm)
        self.assertIn('class="opt off"', html)
        self.assertIn('class="opt rec"', html)

    def test_inbox_card_without_recommendation_when_several_available(self):
        self.stage4_project()
        with mock.patch.object(inbox.image_backends, "detect", return_value=rows(codex=True, qwen=True)):
            card = inbox.imagegen_card_if_needed(self.dir, 4)
        norm = inbox._normalize_card(card, [])
        self.assertIsNone(norm["recommended_option"])
        self.assertNotIn('class="opt rec"', inbox.inbox_page.card_html(norm))
        self.assertEqual(len(norm["options"]), 3)

    def test_inbox_no_card_when_chosen_and_available(self):
        self.stage4_project()
        decisions.decide(self.dir, "storyboard_engine", "codex", "分鏡用 Codex")
        with mock.patch.object(inbox.image_backends, "detect", return_value=rows(codex=True)):
            self.assertIsNone(inbox.imagegen_card_if_needed(self.dir, 4))
        with mock.patch.object(inbox.image_backends, "detect", return_value=rows(codex=False)):
            card = inbox.imagegen_card_if_needed(self.dir, 4)
        self.assertIn("現在不能用", card["title"])

    def test_only_manual_available_still_has_two_options(self):
        self.stage4_project()
        with mock.patch.object(inbox.image_backends, "detect", return_value=rows(codex=False, qwen=False)):
            card = inbox.imagegen_card_if_needed(self.dir, 4)
        problems = []
        inbox._normalize_card(card, problems)
        self.assertEqual(problems, [])
        self.assertEqual(card["options"][0]["label"], "手繪／上傳")
        self.assertIn("我先去裝／登入工具", [o["label"] for o in card["options"]])


if __name__ == "__main__":
    unittest.main()
