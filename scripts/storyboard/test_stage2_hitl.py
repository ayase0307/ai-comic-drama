#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_stage2_hitl.py — 階段 2：人類可讀輸出、人工審核（HITL）與單鏡局部修改同步機制驗證測試套件

測試項目：
(a) 原有的 python scripts/adapt/tests/run_all_tests.py 10 組回歸測試 100% 通過。
(b) sync_script.py：
    1. 核准 EP01-S01 後嘗試偷改劇本，觸發保護機制被鎖定攔截。
    2. 修改未鎖定的 EP01-S02 對白與動作後自動同步至 handoff.json，版號 +1，通過 validate_structure.py。
(c) patch_shot.py：
    1. 將 SH01, SH02 設為 approved（鎖定）。
    2. 嘗試未解鎖修改 SH01 立即被攔截（退出碼非 0）。
    3. 修改未鎖定 SH03 的景別、動作與秒數，驗證 SH01/SH02 100% 不變，時間軸連續重算，版號 +1。
    4. 測試 --absorb-from 秒數吸收保持總時長不變。
    5. 修改後產物通過 validate_storyboard.py 與 layer2_to_table.py --check。

僅使用 Python 標準庫。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Stage2HITLTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cmd(self, cmd, cwd=None):
        import os
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            cmd,
            cwd=cwd or str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def test_01_regression_suite(self):
        """(a) 驗證原有的 10 組回歸測試 100% 通過。"""
        cmd = [sys.executable, str(ROOT / "scripts/adapt/tests/run_all_tests.py")]
        proc = self.run_cmd(cmd)
        self.assertEqual(proc.returncode, 0, f"回歸測試失敗:\n{proc.stderr}\n{proc.stdout}")
        self.assertIn("PASS", proc.stdout)

    def test_02_sync_script_lock_and_sync(self):
        """(b) 驗證 sync_script.py 的鎖定防護與局部同步更新。"""
        # 建立測試用的 2 場景 handoff.json 與 script.md
        script_content = (
            "第01集｜暗流\n\n"
            "1-1 舊公寓客廳 夜/內\n"
            "人物：林澈、沈寧\n"
            "△窗外暴雨拍打玻璃。桌上放著一封濕透的信。\n"
            "沈寧（門外）：開門。我知道你看過那封信。\n"
            "林澈：這字……不是我寫的。\n\n"
            "1-2 舊公寓走廊 夜/外\n"
            "人物：沈寧、趙坤\n"
            "△走廊聲控燈熄滅。沈寧靠著斑駁水泥牆，手按在腰間短刀上。\n"
            "趙坤：人還在裡面？\n"
            "沈寧：他在看信。\n"
        )
        script_file = self.test_path / "script-ep01.md"
        script_file.write_text(script_content, encoding="utf-8")

        handoff_data = {
            "project_id": "test-stage2-proj",
            "rights_status": "owned_original",
            "adaptation_mode": "balanced",
            "genre_mode": "mystery_thriller",
            "aspect_ratio": "9:16",
            "target_medium": "ai_animation",
            "episodes": [
                {
                    "episode_id": "EP01",
                    "title": "測試第01集",
                    "target_duration_seconds": 30,
                    "episode_goal": "建立衝突",
                    "act_out_type": "revelation_twist",
                    "scenes": [
                        {
                            "project_id": "test-stage2-proj",
                            "episode_id": "EP01",
                            "scene_id": "EP01-S01",
                            "source_refs": ["ch01:u1"],
                            "adaptation_mode": "balanced",
                            "setting": {"location": "old_apartment", "time": "night", "interior": True},
                            "characters": ["林澈", "沈寧"],
                            "scene_goal": "林澈發現陌生字跡",
                            "dramatic_turn": "門外傳來沈寧聲音",
                            "action_beats": ["窗外暴雨拍打玻璃。桌上放著一封濕透的信。"],
                            "dialogue": [
                                {"speaker": "沈寧", "text": "開門。我知道你看過那封信。", "audio_type": "offscreen"},
                                {"speaker": "林澈", "text": "這字……不是我寫的。", "audio_type": "onscreen"}
                            ],
                            "props": ["信封"],
                            "continuity_initial": {},
                            "continuity_final": {"letter": "wet"},
                            "estimated_duration_seconds": {"min": 5, "max": 15},
                            "adaptation_changes": [],
                            "storyboard_handoff": {
                                "required_visual_beats": ["窗外暴雨拍打玻璃。桌上放著一封濕透的信。"],
                                "required_audio_beats": [],
                                "must_preserve": ["信封"]
                            }
                        },
                        {
                            "project_id": "test-stage2-proj",
                            "episode_id": "EP01",
                            "scene_id": "EP01-S02",
                            "source_refs": ["ch01:u2"],
                            "adaptation_mode": "balanced",
                            "setting": {"location": "corridor", "time": "night", "interior": False},
                            "characters": ["沈寧", "趙坤"],
                            "scene_goal": "趙坤施壓沈寧",
                            "dramatic_turn": "沈寧暗中防備",
                            "action_beats": ["走廊聲控燈熄滅。沈寧靠著斑駁水泥牆，手按在腰間短刀上。"],
                            "dialogue": [
                                {"speaker": "趙坤", "text": "人還在裡面？", "audio_type": "onscreen"},
                                {"speaker": "沈寧", "text": "他在看信。", "audio_type": "onscreen"}
                            ],
                            "props": ["短刀"],
                            "continuity_initial": {"letter": "wet"},
                            "continuity_final": {"dagger": "ready"},
                            "estimated_duration_seconds": {"min": 5, "max": 15},
                            "adaptation_changes": [],
                            "storyboard_handoff": {
                                "required_visual_beats": ["走廊聲控燈熄滅。沈寧靠著斑駁水泥牆，手按在腰間短刀上。"],
                                "required_audio_beats": [],
                                "must_preserve": ["短刀"]
                            }
                        }
                    ]
                }
            ]
        }
        handoff_file = self.test_path / "handoff-ep01.json"
        handoff_file.write_text(json.dumps(handoff_data, ensure_ascii=False, indent=2), encoding="utf-8")

        # 步驟 1: 將 EP01-S01 設為 approved
        cmd_approve = [
            sys.executable,
            str(ROOT / "scripts/adapt/sync_script.py"),
            "--handoff", str(handoff_file),
            "--scene", "EP01-S01",
            "--set-status", "approved",
            "--note", "S01 第一版導演核准",
        ]
        res = self.run_cmd(cmd_approve)
        self.assertEqual(res.returncode, 0, f"核准失敗:\n{res.stderr}")

        # 檢驗 EP01-S01 是否已鎖定
        data_after_approve = json.loads(handoff_file.read_text(encoding="utf-8"))
        s01_rev = data_after_approve["episodes"][0]["scenes"][0]["review"]
        self.assertEqual(s01_rev["review_status"], "approved")
        self.assertTrue(s01_rev["locked"])

        # 步驟 2: 篡改 script-ep01.md 中 1-1 (S01) 的對白，嘗試同步 -> 應被鎖定攔截！
        tampered_script = script_content.replace("這字……不是我寫的。", "這封信被我撕了！")
        script_file.write_text(tampered_script, encoding="utf-8")

        cmd_sync_fail = [
            sys.executable,
            str(ROOT / "scripts/adapt/sync_script.py"),
            "--handoff", str(handoff_file),
            "--script", str(script_file),
            "--scene", "EP01-S01",
        ]
        res_fail = self.run_cmd(cmd_sync_fail)
        self.assertNotEqual(res_fail.returncode, 0, "已鎖定場景未被攔截！")
        self.assertIn("鎖定攔截", res_fail.stderr + res_fail.stdout)

        # 驗證 handoff 中的內容未被篡改
        data_unmodified = json.loads(handoff_file.read_text(encoding="utf-8"))
        original_line = data_unmodified["episodes"][0]["scenes"][0]["dialogue"][1]["text"]
        self.assertEqual(original_line, "這字……不是我寫的。")

        # 步驟 3: 修改未鎖定的 EP01-S02 (1-2) 對白與動作 -> 應成功同步
        updated_script = tampered_script.replace("他在看信。", "他在客廳裡把信翻到背面了。")
        script_file.write_text(updated_script, encoding="utf-8")

        cmd_sync_s02 = [
            sys.executable,
            str(ROOT / "scripts/adapt/sync_script.py"),
            "--handoff", str(handoff_file),
            "--script", str(script_file),
            "--scene", "EP01-S02",
        ]
        res_s02 = self.run_cmd(cmd_sync_s02)
        self.assertEqual(res_s02.returncode, 0, f"S02 同步失敗:\n{res_s02.stderr}\n{res_s02.stdout}")

        # 驗證 S02 內容已被更新、版號升級、狀態為 pending_review
        data_s02_updated = json.loads(handoff_file.read_text(encoding="utf-8"))
        s02 = data_s02_updated["episodes"][0]["scenes"][1]
        self.assertEqual(s02["dialogue"][1]["text"], "他在客廳裡把信翻到背面了。")
        self.assertEqual(s02["review"]["review_status"], "pending_review")
        self.assertFalse(s02["review"]["locked"])
        self.assertEqual(s02["review"]["revision"], 2)
        self.assertTrue(len(s02["review"]["source_hash"]) > 0)

        # 將 S01 復原原本劇本文字，執行 validate_structure.py 驗證全檔
        restored_script = script_content.replace("他在看信。", "他在客廳裡把信翻到背面了。")
        script_file.write_text(restored_script, encoding="utf-8")
        cmd_validate = [
            sys.executable,
            str(ROOT / "scripts/adapt/validate_structure.py"),
            "--script", str(script_file),
            "--handoff", str(handoff_file),
        ]
        val_res = self.run_cmd(cmd_validate)
        self.assertEqual(val_res.returncode, 0, f"validate_structure 驗證失敗:\n{val_res.stderr}\n{val_res.stdout}")

    def test_03_patch_shot_protection_and_timeline(self):
        """(c) 驗證 patch_shot.py 的審核鎖定、單鏡修改、時間軸自動連續性與校驗通過。"""
        # 建立合規的 4 鏡 Layer 2 JSON
        layer2_sample = {
            "project_id": "TEST_PROJ",
            "scene_id": "EP01-S01",
            "segment_id": "EP01-S01-a",
            "source_scene_id": "EP01-S01",
            "style_lock": {"anchor": "寫實光影", "negative": "低畫質", "lighting_lock_line": "冷色夜光"},
            "metadata": {
                "aspect_ratio": "16:9",
                "target_duration_sec": 12.0,
                "pacing_profile": "Standard_Narrative",
                "lighting_lock_line": "冷鋼夜黑 (#0A0E17 暗部 + 4500K 窗外冷藍側逆光)",
            },
            "continuity_handshake": {"mode": "HARD_CUT_ESTABLISH"},
            "shots": [
                {
                    "shot_id": "SH01",
                    "start_time": 0.0,
                    "end_time": 3.0,
                    "duration": 3.0,
                    "dramatic_beat_type": "Expository_Fast",
                    "camera_optics": {
                        "shot_size": "MLS",
                        "focal_length": "35mm",
                        "physical_distance": "2.0m",
                        "pov_routing": "objective",
                        "movement": "Rack Focus",
                    },
                    "spatial_blocking": {"anchor_objects": ["落地窗"], "blocking_desc": "左A背影，右B推門"},
                    "action_and_performance": {
                        "action_stages": ["A靜立窗前", "B推門走入"],
                        "observable_expression": "A背影沉穩，B神情戒備",
                    },
                    "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True},
                },
                {
                    "shot_id": "SH02",
                    "start_time": 3.0,
                    "end_time": 6.5,
                    "duration": 3.5,
                    "dramatic_beat_type": "Dramatic_Core",
                    "camera_optics": {
                        "shot_size": "CU",
                        "focal_length": "85mm",
                        "physical_distance": "3.5m",
                        "pov_routing": "objective",
                        "movement": "Slow Dolly-in",
                    },
                    "spatial_blocking": {"anchor_objects": ["落地窗"], "blocking_desc": "A側臉近景"},
                    "action_and_performance": {
                        "action_stages": ["A不回頭凝視窗玻璃倒影", "喉結微滾低聲開口"],
                        "observable_expression": "眼簾微垂，眼神冷峻",
                    },
                    "dialogue_and_audio": {
                        "has_dialogue": True,
                        "speaker": "A",
                        "line_verbatim": "你終於來了。",
                        "lips_closed_lock": False,
                    },
                },
                {
                    "shot_id": "SH03",
                    "start_time": 6.5,
                    "end_time": 9.0,
                    "duration": 2.5,
                    "dramatic_beat_type": "Suspense_Delay",
                    "camera_optics": {
                        "shot_size": "ECU",
                        "focal_length": "85mm",
                        "physical_distance": "1.5m",
                        "pov_routing": "objective",
                        "movement": "Tilt Up",
                    },
                    "spatial_blocking": {"anchor_objects": ["白色信封"], "blocking_desc": "B停步於桌角"},
                    "action_and_performance": {
                        "action_stages": ["B雙腳急停", "五指猛然收緊捏皺白色信封"],
                        "observable_expression": "指節用力泛白，紙張折痕明顯",
                    },
                    "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True},
                },
                {
                    "shot_id": "SH04",
                    "start_time": 9.0,
                    "end_time": 12.0,
                    "duration": 3.0,
                    "dramatic_beat_type": "Reaction_OTS",
                    "camera_optics": {
                        "shot_size": "OTS_CU",
                        "focal_length": "100mm",
                        "physical_distance": "6.0m",
                        "pov_routing": "defensive_reaction_ots",
                        "movement": "Static",
                    },
                    "spatial_blocking": {"anchor_objects": ["紅木辦公桌"], "blocking_desc": "越過A右肩拍B"},
                    "action_and_performance": {
                        "action_stages": ["B抬眼望向A背影", "雙唇微顫開口回答"],
                        "observable_expression": "眼眶微紅，下唇微顫",
                    },
                    "dialogue_and_audio": {
                        "has_dialogue": True,
                        "speaker": "B",
                        "line_verbatim": "我不該來的。",
                        "lips_closed_lock": False,
                    },
                },
            ],
            "segment_end_state": {"planned_final_state": {"envelope": "creased"}},
        }
        layer2_file = self.test_path / "layer2-test.json"
        layer2_file.write_text(json.dumps(layer2_sample, ensure_ascii=False, indent=2), encoding="utf-8")

        # 步驟 1: 將 SH01, SH02 簽核為 approved
        for sid in ["SH01", "SH02"]:
            cmd_app = [
                sys.executable,
                str(ROOT / "scripts/storyboard/patch_shot.py"),
                str(layer2_file),
                "--shot", sid,
                "--set-status", "approved",
                "--note", f"{sid} 通過初審",
            ]
            res = self.run_cmd(cmd_app)
            self.assertEqual(res.returncode, 0, f"簽核 {sid} 失敗:\n{res.stderr}")

        # 驗證 SH01, SH02 鎖定狀態
        l2_data = json.loads(layer2_file.read_text(encoding="utf-8"))
        sh01_rev = l2_data["shots"][0]["review"]
        self.assertEqual(sh01_rev["review_status"], "approved")
        self.assertTrue(sh01_rev["locked"])

        # 步驟 2: 嘗試在未帶 --unlock 的情況下修改 SH01 -> 應被鎖定攔截！
        cmd_hack_sh01 = [
            sys.executable,
            str(ROOT / "scripts/storyboard/patch_shot.py"),
            str(layer2_file),
            "--shot", "SH01",
            "--shot-size", "CU",
        ]
        res_hack = self.run_cmd(cmd_hack_sh01)
        self.assertNotEqual(res_hack.returncode, 0, "修改已鎖定鏡頭未被攔截！")
        self.assertIn("鎖定攔截", res_hack.stderr + res_hack.stdout)

        # 步驟 3: 修改未鎖定的 SH03：景別 MS、動作階段、秒數從 2.5s -> 3.5s
        out_md_file = self.test_path / "storyboard.md"
        cmd_patch_sh03 = [
            sys.executable,
            str(ROOT / "scripts/storyboard/patch_shot.py"),
            str(layer2_file),
            "--shot", "SH03",
            "--shot-size", "MS",
            "--action-stages", "B雙腳急停|右手按桌角|猛然捏皺信封",
            "--duration", "3.5",
            "--out-md", str(out_md_file),
            "--check",
        ]
        res_sh03 = self.run_cmd(cmd_patch_sh03)
        self.assertEqual(res_sh03.returncode, 0, f"修改 SH03 失敗:\n{res_sh03.stderr}\n{res_sh03.stdout}")

        # 步驟 4: 驗證 SH01, SH02 100% 不變，時間軸重算無縫連續
        patched_data = json.loads(layer2_file.read_text(encoding="utf-8"))
        shots = patched_data["shots"]

        # SH01 景別依然是 MLS，時長依然 3.0，review 依然 approved
        self.assertEqual(shots[0]["camera_optics"]["shot_size"], "MLS")
        self.assertEqual(shots[0]["review"]["review_status"], "approved")
        self.assertEqual(shots[0]["start_time"], 0.0)
        self.assertEqual(shots[0]["end_time"], 3.0)

        # SH02 時長依然 3.5，start_time=3.0, end_time=6.5
        self.assertEqual(shots[1]["start_time"], 3.0)
        self.assertEqual(shots[1]["end_time"], 6.5)
        self.assertEqual(shots[1]["review"]["review_status"], "approved")

        # SH03 景別變 MS，時長 3.5，start_time=6.5, end_time=10.0，版號+1
        self.assertEqual(shots[2]["camera_optics"]["shot_size"], "MS")
        self.assertEqual(shots[2]["duration"], 3.5)
        self.assertEqual(shots[2]["start_time"], 6.5)
        self.assertEqual(shots[2]["end_time"], 10.0)
        self.assertEqual(shots[2]["action_and_performance"]["action_stages"], ["B雙腳急停", "右手按桌角", "猛然捏皺信封"])
        self.assertEqual(shots[2]["review"]["review_status"], "pending_review")
        self.assertEqual(shots[2]["review"]["revision"], 2)

        # SH04 start_time 順延至 10.0, end_time=13.0
        self.assertEqual(shots[3]["start_time"], 10.0)
        self.assertEqual(shots[3]["end_time"], 13.0)

        # 總時長更新為 13.0
        self.assertEqual(patched_data["metadata"]["target_duration_sec"], 13.0)

        # 驗證 Markdown 表已產生且包含審核燈號
        self.assertTrue(out_md_file.exists())
        md_text = out_md_file.read_text(encoding="utf-8")
        self.assertIn("✅ approved", md_text)
        self.assertIn("⏳ pending_review (rev 2)", md_text)

        # 步驟 5: 驗證通過 layer2_to_table.py --check
        cmd_ltt_check = [
            sys.executable,
            str(ROOT / "scripts/storyboard/layer2_to_table.py"),
            str(layer2_file),
            "--check",
        ]
        res_ltt = self.run_cmd(cmd_ltt_check)
        self.assertEqual(res_ltt.returncode, 0, f"layer2_to_table --check 失敗:\n{res_ltt.stderr}\n{res_ltt.stdout}")

        # 步驟 6: 驗證通過 validate_storyboard.py
        cmd_val_sb = [
            sys.executable,
            str(ROOT / "scripts/storyboard/validate_storyboard.py"),
            "--file", str(layer2_file),
        ]
        res_sb = self.run_cmd(cmd_val_sb)
        self.assertEqual(res_sb.returncode, 0, f"validate_storyboard 失敗:\n{res_sb.stderr}\n{res_sb.stdout}")

        # 步驟 7: 測試 --absorb-from 功能（將 SH03 調整至 3.0s，由未鎖定的 SH04 吸收 0.5s，總時長維持 13.0s）
        cmd_absorb = [
            sys.executable,
            str(ROOT / "scripts/storyboard/patch_shot.py"),
            str(layer2_file),
            "--shot", "SH03",
            "--duration", "3.0",
            "--absorb-from", "SH04",
            "--check",
        ]
        res_abs = self.run_cmd(cmd_absorb)
        self.assertEqual(res_abs.returncode, 0, f"absorb 測試失敗:\n{res_abs.stderr}\n{res_abs.stdout}")

        data_abs = json.loads(layer2_file.read_text(encoding="utf-8"))
        self.assertEqual(data_abs["shots"][2]["duration"], 3.0)
        self.assertEqual(data_abs["shots"][3]["duration"], 3.5)
        self.assertEqual(data_abs["metadata"]["target_duration_sec"], 13.0)
        self.assertEqual(data_abs["shots"][2]["start_time"], 6.5)
        self.assertEqual(data_abs["shots"][2]["end_time"], 9.5)
        self.assertEqual(data_abs["shots"][3]["start_time"], 9.5)
        self.assertEqual(data_abs["shots"][3]["end_time"], 13.0)


if __name__ == "__main__":
    unittest.main()
