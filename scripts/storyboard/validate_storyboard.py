#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 電影與漫劇分鏡靜態驗證與品質審查器 (Storyboard Quality Linter v2.0)
零外部依賴，執行七大硬核工程驗證：
1. 時長守恆檢查 (各鏡頭秒數加總 == 目標切片總時長)
2. 台詞 100% 一字不差保真與語速超載檢查 (防止刪詞、捏造或倍速嘴瓢)
3. 偽精確度與醫學解剖學黑名單攔截 (攔截「眼輪匝肌、降口角肌、嘴角下垂3mm、流體折射率、@lmage」)
4. 視角與武戲遮擋衝突檢查 (高速打擊/碰撞瞬間嚴禁使用 Dirty Frame 遮擋接觸點，強制 90° 無遮擋)
5. 景別與五官粒度檢查 (遠景 ELS/LS 嚴禁描寫面部五官微表情)
6. 雙模式跨組握手與 Observed > Planned 狀態檢查 (時空跳躍必須走 HARD_CUT_ESTABLISH)
7. 9:16 直式短劇安全區與縱深構圖檢查
"""

import argparse
import difflib
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handoff_to_skeleton import MAX_SHOT_SEC, find_todo, segment_sort_key  # noqa: E402
from speech_utils import count_speech_chars, normalize_speech  # noqa: E402
from audit_refs_and_segments import effective_duration  # noqa: E402
from move_lint import lint_segment_moves  # noqa: E402
from director_lint import lint_director, lint_segment_seam  # noqa: E402
from dialogue_density import (  # noqa: E402
    LINE_SUGGEST_MAX, ONSCREEN_RATE_WARN, SPEECH_SHARE_WARN, VO_RATE_WARN,
    check_dialogue_density, is_voiceover_line, rate_limits, shot_lines,
)
import dual_lead_in  # noqa: E402
import action_marks  # noqa: E402
import h3_spec  # noqa: E402
from shot_intent import cross_segment_intent_errors, segment_intent_errors, shot_intent_errors  # noqa: E402

BEAT_TYPES = ("Expository_Fast", "Suspense_Delay", "Dramatic_Core", "Combat_Impact", "Reaction_OTS")
# Fast_Dialogue（EP01 findings #6）：快節奏對話（#116 角色語速、#120 1.2 s 鏡長下限），長篇模式的文戲用它，
# 不必借 Fast_ShortDrama（那是直式短劇／高燃打鬥）。只是 enum 標籤，不改任何門檻。
PACING_PROFILES = ("Slow_Cinematic", "Standard_Narrative", "Fast_ShortDrama", "Fast_Dialogue")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

if sys.platform.startswith("win"):
    for _st in (sys.stdout, sys.stderr):
        if hasattr(_st, "reconfigure"):
            _st.reconfigure(encoding="utf-8", errors="replace")

# 嚴格攔截之偽精確度、醫學解剖學與 OCR 損壞詞黑名單
FORBIDDEN_PSEUDO_TERMS = [
    "眼輪匝肌", "眼轮匝肌",
    "降口角肌",
    "額肌", "额肌",
    "嘴角下垂3mm", "嘴角下垂 3mm", "2mm", "3mm",
    "折射率", "表面張力表現", "表面张力表现",
    "@lmage", "Negative PrompU", "叫(物理音效)"
]

# 嚴格攔截之子代理偷懶罐頭詞與萬用廢話黑名單（防止 Goodhart's Law 批量造假）
FORBIDDEN_BOILERPLATE_PHRASES = [
    "微風掠過衣擺，光影保持自然抖動",
    "衣角與髮絲隨動作慣性自然下垂",
    "executes deliberate physical blocking with natural body movement",
    "Then the motion transitions smoothly",
    "executing choreographed actions with emotional continuity",
]



_KIND_OK = {
    "obj": lambda v: isinstance(v, dict),
    "list": lambda v: isinstance(v, list),
    "str": lambda v: isinstance(v, str),
    "bool": lambda v: isinstance(v, bool),
    "num": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}
_KIND_LABEL = {"obj": "JSON 物件", "list": "陣列", "str": "字串", "bool": "布林值", "num": "數字"}


def _tname(value) -> str:
    names = {dict: "物件", list: "陣列", str: "字串", bool: "布林值", int: "整數", float: "小數", type(None): "null"}
    return names.get(type(value), type(value).__name__)


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _expect(container: dict, key: str, kind: str, path: str, errors: list, nullable: bool = False) -> None:
    """key 存在時才檢查型別；缺少的欄位交給各檢查的預設值處理。"""
    if key not in container or (container[key] is None and nullable):
        return
    if not _KIND_OK[kind](container[key]):
        suffix = "（或 null）" if nullable else ""
        errors.append(f"[格式錯誤] {path}.{key} 應為{_KIND_LABEL[kind]}{suffix}，實際為{_tname(container[key])}")


def _shot_format_errors(shot, path: str) -> list:
    if not isinstance(shot, dict):
        return [f"[格式錯誤] {path} 應為 JSON 物件，實際為{_tname(shot)}"]
    errors: list = []
    _expect(shot, "shot_id", "str", path, errors)
    _expect(shot, "duration", "num", path, errors)
    _expect(shot, "dramatic_beat_type", "str", path, errors)
    for key in ("camera_optics", "action_and_performance", "dialogue_and_audio", "shot_intent", "choice_why"):
        _expect(shot, key, "obj", path, errors)
    for key in ("shot_size", "pov_routing", "physical_distance"):
        _expect(_as_dict(shot.get("camera_optics")), key, "str", f"{path}.camera_optics", errors)
    act = _as_dict(shot.get("action_and_performance"))
    _expect(act, "observable_expression", "str", f"{path}.action_and_performance", errors)
    _expect(act, "action_stages", "list", f"{path}.action_and_performance", errors)
    stages = act.get("action_stages") if isinstance(act.get("action_stages"), list) else []
    for i, stage in enumerate(stages):
        if not isinstance(stage, str):
            errors.append(f"[格式錯誤] {path}.action_and_performance.action_stages[{i}] 應為字串，實際為{_tname(stage)}")
    dlg = _as_dict(shot.get("dialogue_and_audio"))
    _expect(dlg, "line_verbatim", "str", f"{path}.dialogue_and_audio", errors, nullable=True)
    return errors


def layer2_format_errors(data) -> list:
    """Layer 2 分鏡檔的型別檢查，錯誤訊息帶 JSON 路徑；有錯時不再往下跑業務檢查。"""
    if not isinstance(data, dict):
        return [f"[格式錯誤] $ 應為 JSON 物件，實際為{_tname(data)}"]
    errors: list = []
    for key in ("project_id", "scene_id", "segment_id", "source_scene_id"):
        _expect(data, key, "str", "$", errors, nullable=key != "project_id")
    for key in ("metadata", "continuity_handshake"):
        _expect(data, key, "obj", "$", errors)
    _expect(data, "shots", "list", "$", errors)
    _expect(_as_dict(data.get("metadata")), "target_duration_sec", "num", "$.metadata", errors)
    _expect(_as_dict(data.get("metadata")), "lighting_lock_line", "str", "$.metadata", errors)
    handshake = _as_dict(data.get("continuity_handshake"))
    for key in ("overflow_dialogue_in", "overflow_dialogue_out"):
        _expect(handshake, key, "str", "$.continuity_handshake", errors, nullable=True)
    shots = data.get("shots") if isinstance(data.get("shots"), list) else []
    for idx, shot in enumerate(shots):
        errors += _shot_format_errors(shot, f"$.shots[{idx}]")
    return errors


def handoff_format_errors(handoff) -> list:
    """handoff JSON 的結構檢查：episodes 必須是陣列、場景與台詞項目必須是物件且 text 為字串。"""
    if not isinstance(handoff, dict):
        return [f"[格式錯誤] $ 應為 JSON 物件，實際為{_tname(handoff)}"]
    episodes = handoff.get("episodes")
    if not isinstance(episodes, list):
        return [f"[格式錯誤] $.episodes 應為陣列，實際為{_tname(episodes) if episodes is not None else '缺少'}"]
    errors: list = []
    for i, episode in enumerate(episodes):
        ep_path = f"$.episodes[{i}]"
        if not isinstance(episode, dict):
            errors.append(f"[格式錯誤] {ep_path} 應為 JSON 物件，實際為{_tname(episode)}")
            continue
        scenes = episode.get("scenes")
        if not isinstance(scenes, list):
            errors.append(f"[格式錯誤] {ep_path}.scenes 應為陣列，實際為{_tname(scenes) if scenes is not None else '缺少'}")
            continue
        for j, scene in enumerate(scenes):
            sc_path = f"{ep_path}.scenes[{j}]"
            if not isinstance(scene, dict):
                errors.append(f"[格式錯誤] {sc_path} 應為 JSON 物件，實際為{_tname(scene)}")
                continue
            if not isinstance(scene.get("scene_id"), str):
                errors.append(f"[格式錯誤] {sc_path}.scene_id 缺少或不是字串")
            dialogue = scene.get("dialogue", [])
            if not isinstance(dialogue, list):
                errors.append(f"[格式錯誤] {sc_path}.dialogue 應為陣列，實際為{_tname(dialogue)}")
                continue
            for k, line in enumerate(dialogue):
                line_path = f"{sc_path}.dialogue[{k}]"
                if not isinstance(line, dict):
                    errors.append(f"[格式錯誤] {line_path} 應為 JSON 物件，實際為{_tname(line)}")
                elif not isinstance(line.get("text"), str):
                    errors.append(f"[格式錯誤] {line_path}.text 缺少或不是字串")
    return errors


def dialogue_verbatim_errors(expected: list, actual: list) -> list:
    """逐句比對（依順序），只在整段串接比對失敗時使用，用來指出是哪一句缺、改、或多出。"""
    exp = [t.strip() for t in expected if t and t.strip()]
    act = [t.strip() for t in actual if t and t.strip()]
    if exp == act:
        return []
    errors = []
    matcher = difflib.SequenceMatcher(a=exp, b=act, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "delete":
            errors += [f"[台詞保真鐵律違規] 缺少台詞：「{t}」" for t in exp[i1:i2]]
        elif tag == "insert":
            errors += [f"[台詞保真鐵律違規] 多出未見於劇本的台詞：「{t}」" for t in act[j1:j2]]
        elif tag == "replace" and i2 - i1 == j2 - j1:
            errors += [f"[台詞保真鐵律違規] 台詞被改寫：劇本「{old}」→ 分鏡「{new}」"
                       for old, new in zip(exp[i1:i2], act[j1:j2])]
        else:
            errors += [f"[台詞保真鐵律違規] 缺少或被改寫的劇本台詞：「{t}」" for t in exp[i1:i2]]
            errors += [f"[台詞保真鐵律違規] 分鏡中多出或被改寫的台詞：「{t}」" for t in act[j1:j2]]
    return errors


def verbatim_check(expected: list, actual: list) -> list:
    """台詞保真：去標點與空白後，把整場台詞串成一個字串比對，允許 J-Cut 切段；
    串接結果不同時，先指出第一個不一致的位置，再列出逐句差異。"""
    exp_text = normalize_speech("".join(t for t in expected if t))
    act_text = normalize_speech("".join(t for t in actual if t))
    if exp_text == act_text:
        return []
    i = next((k for k, (a, b) in enumerate(zip(exp_text, act_text)) if a != b),
             min(len(exp_text), len(act_text)))
    lo, hi = max(0, i - 8), i + 8
    head = (f"[台詞保真鐵律違規] 去標點後第 {i + 1} 字起不一致（劇本 {len(exp_text)} 字／分鏡 {len(act_text)} 字）："
            f"劇本「…{exp_text[lo:hi]}…」→ 分鏡「…{act_text[lo:hi]}…」")
    return [head] + dialogue_verbatim_errors(expected, actual)


def _first_dialogue(data: dict) -> str:
    """段內第一句有台詞的鏡頭台詞（normalize 後）；沒有則回傳空字串。"""
    for shot in data.get("shots", []):
        dlg = _as_dict(shot.get("dialogue_and_audio"))
        if dlg.get("has_dialogue") and (dlg.get("line_verbatim") or "").strip():
            return normalize_speech(dlg["line_verbatim"])
    return ""


def _overflow(data: dict, key: str) -> str:
    return (_as_dict(data.get("continuity_handshake")).get(key) or "").strip()


def dialogue_stream(segments: list) -> list:
    """依段序收集各鏡的 line_verbatim。overflow 欄位只是註記，不計入台詞串流：
    跨段的句子必須已逐字寫在下一段首句（見 jcut_errors），否則串流會缺字。"""
    pieces = []
    for data in segments:
        for shot in data.get("shots", []):
            dlg = _as_dict(shot.get("dialogue_and_audio"))
            if dlg.get("has_dialogue") and (dlg.get("line_verbatim") or "").strip():
                pieces.append(dlg["line_verbatim"].strip())
    return pieces


def jcut_errors(segments: list) -> list:
    """J-Cut 順延一致性（segments 依段序）：上一段 overflow_dialogue_out 必須逐字出現在下一段第一句台詞；
    下一段 overflow_dialogue_in 必須等於上一段的 out；最後一段不得有 out。"""
    errors = []
    for prev, cur in zip(segments, segments[1:]):
        cur_id = cur.get("segment_id", cur.get("scene_id", ""))
        out_raw = _overflow(prev, "overflow_dialogue_out")
        in_raw = _overflow(cur, "overflow_dialogue_in")
        if in_raw and normalize_speech(in_raw) != normalize_speech(out_raw):
            errors.append(f"[J-Cut 順延不一致] {cur_id}：overflow_dialogue_in「{in_raw}」與上一段 overflow_dialogue_out「{out_raw}」不同")
        if out_raw and normalize_speech(out_raw) not in _first_dialogue(cur):
            errors.append(f"[J-Cut 順延不一致] {cur_id}：上一段 overflow_dialogue_out「{out_raw}」未逐字出現在本段第一句台詞（須寫進 line_verbatim）")
    if segments:
        last = segments[-1]
        if _overflow(last, "overflow_dialogue_out"):
            errors.append(f"[J-Cut 順延不一致] {last.get('segment_id', last.get('scene_id', ''))}：最後一段不應有 overflow_dialogue_out")
    return errors


def scene_key(data: dict) -> str:
    """layer2 檔對應的來源場景 ID：source_scene_id → scene_id → segment_id 去掉 -a…-z、-aa… 段尾。"""
    if data.get("source_scene_id"):
        return data["source_scene_id"]
    if data.get("scene_id"):
        return data["scene_id"]
    return re.sub(r"-[a-z]+$", "", data.get("segment_id", ""))


def load_handoff_dialogues(handoff: dict) -> dict:
    """{scene_id: [台詞原文, ...]}，依 handoff 的集與場順序。"""
    return {
        scene["scene_id"]: [line["text"] for line in scene.get("dialogue", [])]
        for episode in handoff.get("episodes", [])
        for scene in episode.get("scenes", [])
    }


SHOT_SIZES = ("ELS", "LS", "MLS", "MS", "MCU", "CU", "ECU", "OTS_MS", "OTS_CU")
CLOSE_SHOT_SIZES = ("MS", "MCU", "CU", "ECU", "OTS_MS", "OTS_CU")  # 6e：中景以內的主鏡
SHOT_SIZE_ALIASES = {"WS": "LS", "EWS": "ELS", "XLS": "ELS", "MWS": "MLS", "OTS": "OTS_MS 或 OTS_CU", "XCU": "ECU", "BCU": "ECU"}


def validate_storyboard_data(data: dict, original_script_dialogues: list = None, ref_ids: set = None,
                             voice_only_ids: set = None) -> dict:
    """ref_ids：有參考包或設定圖的角色 id（load_reference_ids 由專案根目錄讀）；給了才跑 6e。"""
    format_errors = layer2_format_errors(data)
    if format_errors:
        return {"passed": False, "errors": format_errors, "warnings": [], "checks_passed": []}
    errors = []
    warnings = []
    checks_passed = []

    errors += find_todo(data)

    meta = data.get("metadata", {})
    target_dur = float(meta.get("target_duration_sec", 0))
    aspect = meta.get("aspect_ratio", "16:9")
    lighting_lock = meta.get("lighting_lock_line", "").strip()

    # Check 0: 光影鎖定線不可為空 (防止 v6.1 禁光影錯誤)
    if not lighting_lock:
        errors.append("[C-02 光影缺失錯誤] metadata.lighting_lock_line 為空！嚴禁卸載光影描述，否則跨鏡頭必然跳色。")
    else:
        checks_passed.append("[PASS] 全域光影與色卡鎖定線已確立")

    shots = data.get("shots", [])
    if not shots:
        errors.append("[結構錯誤] shots 陣列為空！")
        return {"passed": False, "errors": errors, "warnings": warnings, "checks_passed": checks_passed}

    # Check 1: 時長加總守恆
    total_shot_dur = round(sum(float(s.get("duration", 0)) for s in shots), 2)
    if abs(total_shot_dur - target_dur) > 0.15:
        errors.append(f"[時長不守恆] 鏡頭時長總和 ({total_shot_dur}s) != 目標總時長 ({target_dur}s)")
    else:
        checks_passed.append(f"[PASS] 時長守恆核對通過 ({total_shot_dur}s == {target_dur}s，共 {len(shots)} 鏡)")

    warnings += lint_segment_moves(shots)  # PR-14c 運鏡導演助手（warning）
    warnings += lint_director(shots)  # PR-15c 導演層 lint（warning）

    # Check 1b: H3 取整後的切點可行性（與 audit_refs_and_segments E4、編譯器同一組常數 h3_spec.MIN_SHOT_SEC／
    # SHOT_SOFT_MIN_SEC，提前到階段 4 攔截）：每鏡平均 < 1.2 s 擋；1.2–2.0 s 只提醒（未在 H3 實測）。
    if len(shots) > 1 and target_dur > 0:
        # 有合法的 metadata.frames（17n+5）就直接用它；否則由秒數換算（h3_spec 已吸附浮點誤差，SB-2）
        meta_frames = meta.get("frames")
        if isinstance(meta_frames, int) and not isinstance(meta_frames, bool) and h3_spec.is_quantum(meta_frames):
            eff_d = h3_spec.seconds_for_frames(meta_frames)
        else:
            eff_d = effective_duration(target_dur)
        hard, soft = h3_spec.MIN_SHOT_SEC, h3_spec.SHOT_SOFT_MIN_SEC
        need = hard * len(shots)
        if eff_d - 0.05 < need:
            errors.append(
                f"[E4 切點不可行] {len(shots)} 鏡分段取整後只有 {eff_d:.3f}s，首切/間隔/收尾各需 >= {hard:g}s（共 {need:.1f}s）。"
                f"請把本段延長到 >= {need + 0.5:.1f}s 或減少鏡頭數。"
            )
        elif eff_d - 0.05 < soft * len(shots):
            warnings.append(
                f"[W:E4 短鏡] {len(shots)} 鏡分段取整後 {eff_d:.3f}s，平均每鏡不到 {soft:g}s"
                f"（≥{hard:g}s 合規；<{soft:g}s 未在 H3 實測，出片後核對切點）。"
            )

    # Check 1c: enum 合法性
    pacing = meta.get("pacing_profile")
    if pacing and pacing not in PACING_PROFILES:
        errors.append(f"[enum 錯誤] metadata.pacing_profile '{pacing}' 不在 {PACING_PROFILES}")

    # 收集所有分鏡台詞與文本
    close_up_count = 0

    for idx, s in enumerate(shots, 1):
        sid = s.get("shot_id", f"SH{idx:02d}")
        dur = float(s.get("duration", 1.0))
        if dur > MAX_SHOT_SEC:
            errors.append(f"[{sid} 鏡頭過長] 鏡頭時長 {dur}s 超過 {MAX_SHOT_SEC:.0f} 秒（H3 單鏡上限），請拆成兩鏡。")
        # Check 0b: 鏡頭意圖先於技術欄位（I01–I03、I05），規範見 references/storyboard/shot-intent.md
        errors += shot_intent_errors(s, sid)
        beat_type = s.get("dramatic_beat_type", "")
        if beat_type and beat_type not in BEAT_TYPES:
            errors.append(f"[{sid} enum 錯誤] dramatic_beat_type '{beat_type}' 不在 {BEAT_TYPES}")
        _act = s.get("action_and_performance", {}) or {}
        if not _act.get("action_stages_en") and any(_CJK_RE.search(x or "") for x in _act.get("action_stages", []) if isinstance(x, str)):
            warnings.append(f"[{sid} 英文動作缺漏] action_stages 為中文且未提供 action_stages_en；階段 5 編譯 H3 英文提示詞會觸發 E15，請補英譯。")
        cam = s.get("camera_optics", {})
        shot_size = cam.get("shot_size", "MS")
        pov_routing = cam.get("pov_routing", "objective")
        if shot_size not in SHOT_SIZES:
            hint = SHOT_SIZE_ALIASES.get(str(shot_size).upper())
            errors.append(
                f"[{sid} enum 錯誤] camera_optics.shot_size '{shot_size}' 不在 {SHOT_SIZES}"
                + (f"；請改用 {hint}" if hint else "")
            )
        phys_dist = cam.get("physical_distance", "")

        act = s.get("action_and_performance", {})
        stages = act.get("action_stages", [])
        expr = act.get("observable_expression", "")
        dlg = s.get("dialogue_and_audio", {})

        if shot_size in ("MCU", "CU", "ECU", "OTS_CU"):
            close_up_count += 1

        # Check 2: 物理物距是否標註
        if not phys_dist:
            warnings.append(f"[{sid}] 未明確標註攝影機物理物距 (physical_distance)，可能削弱焦段透視表現。")

        # Check 3: 單鏡動作拆解 <= 5 階段上限
        if len(stages) > 5:
            errors.append(f"[{sid} 動作過載] 單鏡動作拆解達 {len(stages)} 個階段 (上限為 5 階段)，極易引發模型果凍化形變！")

        # Check 4: 武戲碰撞 vs Dirty Frame 遮擋衝突檢查
        if beat_type == "Combat_Impact" and pov_routing == "dirty_frame_20_35":
            errors.append(
                f"[{sid} 視角遮擋衝突] 武戲打擊瞬間 (Combat_Impact) 嚴禁使用 Dirty Frame 前景遮擋！"
                f"必須切換為 clear_impact_90deg (90度垂直軸線無遮擋) 以免擋住打擊接觸點！"
            )

        # Check 5: 遠景/全景零五官微表情檢查與遠景多人同框提醒
        if shot_size in ("ELS", "LS"):
            if any(k in expr for k in ["瞳孔", "睫毛", "嘴角", "眼眶", "淚", "唇"]):
                errors.append(f"[{sid} 景別粒度錯誤] 當前景別為遠/全景 ({shot_size})，臉部像素極小，嚴禁描寫五官細節 ({expr})！")
            
            # 遠景人物崩壞警告：多名角色同框且未標註背影/剪影
            shot_text = f"{' '.join(stages)} {expr} {s.get('spatial_blocking', {}).get('blocking_desc', '')}"
            has_multiple_chars = (
                len(s.get("character_ids", [])) > 1
                or any(k in shot_text for k in ["兩人", "两人", "眾人", "众人", "群戲", "群戏", "雙方", "双方", "對峙", "对峙"])
                or bool(re.search(r"(@[^\s,，。]+.*@[^\s,，。]+)", shot_text))
            )
            has_back_view = any(k in shot_text.lower() for k in [
                "背影", "back view", "from behind", "silhouette", "剪影", "不露臉", "不露脸"
            ])
            if has_multiple_chars and not has_back_view:
                warnings.append(
                    f"[{sid}] 💡 H3 遠景人物提醒：H3 遠景多人同框容易不照參考圖（臉崩），"
                    f"建議改用「一鏡一臉特寫」演反應，或用「背影（不露臉）」演群戲走位。"
                )

        # Check 5b（僅警告）：同框主要人物 >2。依據是上游「三人以上同框易漂移」，H3 上尚未量化 2 人 vs 1 人的差別。
        n_chars = len([c for c in s.get("character_ids", []) if c and "旁白" not in str(c)])
        if n_chars > 2:
            warnings.append(
                f"[{sid}] 同框主要人物 {n_chars} 人 (>2)：多人同框易串臉，建議拆成單人反應鏡或讓多出的人不露臉"
                "（骨架階段會把整場角色填進每鏡，可於細化後再看）。"
            )

        # Check 6: 偽精確度與醫學解剖學黑名單掃描
        raw_shot_str = json.dumps(s, ensure_ascii=False)
        for bad_word in FORBIDDEN_PSEUDO_TERMS:
            if bad_word in raw_shot_str:
                errors.append(f"[{sid} 偽精確/解剖詞污染] 檢測到禁用詞「{bad_word}」，請轉譯為可見外顯五官動作！")

        # Check 6b: 防偷懶罐頭詞與萬用廢話黑名單攔截
        for bp_word in FORBIDDEN_BOILERPLATE_PHRASES:
            if bp_word in raw_shot_str:
                errors.append(
                    f"[{sid} 偷懶罐頭詞攔截] 檢測到禁用萬用罐頭句「{bp_word}」！"
                    f"必須依該場次真實環境（如室內餐廳日光燈、塵埃飛散、桌面震動）撰寫具象物理細節，嚴禁複製貼上！"
                )

        # Check 6c: H3 物理穿模高風險攔截（單顆打擊鏡同時塞入主角＋路人＋手持道具＋異獸四方碰撞）
        blocking_desc = s.get("spatial_blocking", {}).get("blocking_desc", "")
        anchors_str = " ".join(s.get("spatial_blocking", {}).get("anchor_objects", []))
        combined_visual = f"{' '.join(stages)} {blocking_desc} {anchors_str}"
        has_npc_victim = any(k in combined_visual for k in ["幼童", "小孩", "婦人", "路人", "店員", "食客", "母子"])
        has_creature = any(k in combined_visual for k in ["巨鼠", "巨蟒", "異獸", "妖獸", "怪物", "巨獸"])
        has_prop_strike = any(k in combined_visual for k in ["鐵凳", "圓凳", "椅子", "砸向", "掄起"])
        if beat_type == "Combat_Impact" and has_npc_victim and has_creature and has_prop_strike:
            errors.append(
                f"[{sid} H3 多主體碰撞穿模攔截] 單顆戰鬥鏡頭同時塞入「主角＋無錨定路人＋手持道具＋異獸」四方碰撞，"
                f"實測必然導致鐵凳懸空吸附鼠鼻與路人衣服被染色！請拆分為："
                f"① 主角瞳孔驟縮／時間減速感知抄起道具特寫 ➔ ② 90度純粹道具轟中異獸部位特寫（最多2主體） ➔ ③ 異獸受擊翻滾撞翻家具。"
            )

        # Check 6d: 無參考圖路人單獨佔據中近景/特寫主鏡攔截
        # 已錨定主體：鏡頭有 character_ids，或文字點名了本段登記的角色名／專案指定的名單
        # （metadata.anchored_names；舊專案的預設名單保留在 LEGACY_ANCHORED_NAMES 以維持相容）。
        anchored_names = list(LEGACY_ANCHORED_NAMES) + _segment_anchor_names(data)
        has_protagonist_or_creature = (
            any(k and k in combined_visual for k in anchored_names)
            or bool(_PLACEHOLDER_ROLE_RE.search(combined_visual))
            or len(s.get("character_ids", [])) > 0
        )
        is_back_or_partial = any(
            k in combined_visual.lower() for k in ["背影", "剪影", "失焦", "局部", "畫外音", "back view", "silhouette", "blurred"]
        )
        # Check 6e（SB-4）：改以角色表／包清單比對——character_ids 裡沒有參考包也沒有設定圖的角色佔 MS 以上主鏡
        # （關鍵字清單擋不到「導遊」這類配角；REMIX refcheck E50 要到階段 5 才擋）。只警告：階段 4 時包可能還沒建。
        if ref_ids is not None and shot_size in CLOSE_SHOT_SIZES and not is_back_or_partial:
            _hidden_ids = set(str(x) for x in (s.get("no_visual_reference_ids") or [])) \
                | set(str(x) for x in ((data.get("asset_refs") or {}).get("no_visual_reference_ids") or []))
            _unref = [c for c in (s.get("character_ids") or [])
                      if c and "旁白" not in str(c) and not str(c).upper().startswith(("NARRATOR", "VO-", "N-"))
                      and c not in ref_ids and c not in (voice_only_ids or set()) and c not in _hidden_ids]
            if _unref:
                warnings.append(
                    f"[{sid} 6e 無參考包角色主鏡] {'、'.join(map(str, _unref))} 沒有角色包／設定圖，卻在 {shot_size} 主鏡；"
                    f"H3／REMIX 會照文字自由發揮、每段長得不一樣。進階段 5 前補階段 2 設定圖或 ejin3／REMIX 包"
                    f"（assets/character-packs.json），或改背影／失焦／畫外音。")
        if has_npc_victim and not has_protagonist_or_creature and not is_back_or_partial and shot_size in ("MS", "MCU", "CU", "ECU"):
            errors.append(
                f"[{sid} 無參考圖路人主鏡畫風漂移攔截] 鏡頭以無設定圖之路人（如幼童/婦人）作為 {shot_size} 正面主體，"
                f"H3 在缺乏人物參考圖錨定時必然漂移成異質真人實拍風！請改用背影/前景失焦局部，或改拍已綁定參考圖之主角反應特寫。"
            )

        # Check 7: 台詞語速與閉唇鎖檢查（v118 #4：依畫內／VO 分線，和 #116 角色語速一致）
        if dlg.get("has_dialogue"):
            spoken = shot_lines(dlg)
            if spoken:
                n_chars = sum(count_speech_chars(t) for t in spoken)
                cps = n_chars / max(dur, 0.5)
                rate_warn, rate_max = rate_limits(dlg)
                kind = "旁白／內心 VO" if is_voiceover_line(dlg) else "畫內對嘴"
                line = "／".join(spoken)
                if cps > rate_max + 1e-9:
                    errors.append(
                        f"[{sid} 語速超載] 台詞「{line}」({n_chars}字 / {dur}s = {cps:.1f}字/秒) 超出{kind}上限 {rate_max} 字/秒！"
                        f"請於氣口切斷並順延至 overflow_dialogue_out，或把鏡長拉到 字數÷語速＋0.3s。"
                    )
                elif cps > rate_warn + 1e-9 or max(count_speech_chars(t) for t in spoken) > LINE_SUGGEST_MAX:
                    warnings.append(
                        f"[{sid}] ⚠️ 台詞超速風險：本鏡 {n_chars} 字 {dur} 秒（{kind}建議 ≤ {rate_warn} 字/秒、單句 ≤ {LINE_SUGGEST_MAX} 字）"
                    )
        else:
            _vis = " ".join(str(x) for x in [expr, *stages, (s.get("visual_description") or "")] if x).lower()
            _hidden = any(k in _vis for k in ["背影", "剪影", "失焦", "局部", "back view", "silhouette", "blurred", "空景", "手部", "hand"])
            _face_visible = bool(s.get("character_ids")) and shot_size not in ("ELS", "LS") and not _hidden
            if _face_visible and not dlg.get("lips_closed_lock", False):
                warnings.append(f"[{sid} 閉唇鎖提醒] 鏡頭無台詞，建議將 lips_closed_lock 設為 true 防止角色亂動嘴。")

    # Check 7d: 同段鏡頭意圖／理由不准複製（I04、I05）
    errors += segment_intent_errors(shots)
    _de, _dw = check_dialogue_density(data)  # PR #118 分鏡台詞密度閘門（不計雙人引子與原著無台詞動作鏡）
    errors += _de
    warnings += _dw
    # D5（單段：【動作】鏡被合併／截短）、D6（無台詞鏡塞 ≥3 個主要動作）
    _ae, _aw = action_marks.segment_issues(data, _segment_anchor_names(data))
    errors += _ae
    warnings += _aw

    # Check 8: asset_refs 佔位符（#43：骨架的 TODO／S-item1／C-item2 不可原樣通過）
    _refs = data.get("asset_refs") or {}
    _ph = re.compile(r"^(TODO.*|[A-Z]-item\d+)$")
    _bad = []
    if isinstance(_refs.get("scene_id"), str) and _ph.match(_refs["scene_id"]):
        _bad.append(f"scene_id={_refs['scene_id']}")
    for _c in (_refs.get("characters") or []) + (_refs.get("creatures") or []):
        if isinstance(_c, dict):
            for _k in ("id", "costume_id"):
                if isinstance(_c.get(_k), str) and _ph.match(_c[_k]):
                    _bad.append(f"{_k}={_c[_k]}")
    if _bad:
        warnings.append("[asset_refs 佔位符] 仍有骨架佔位值未替換：" + "、".join(_bad[:6]) + "；請改成 assets.md／bible.json 內真實的 ID。")

    # Check 8b（#46）：場景結尾有不可逆破壞，卻仍附含該道具的場景母版 → 警告（母版會把已毀道具畫回來）
    _pws = " ".join(str(x) for x in ((data.get("continuity_handshake") or {}).get("persistent_world_state") or []))
    _irrev = re.search(r"destroyed|shattered|burst|exploded|burned|broken|爆裂|破壞|毀|碎|燒毀|崩", _pws, re.I)
    _meta = data.get("metadata") or {}
    if _irrev and not _meta.get("scene_master_disabled"):
        warnings.append("[不可逆狀態仍附場景母版] persistent_world_state 含已破壞／已毀狀態（"
                        + _irrev.group(0) + "）；含該道具的場景母版會讓生圖把它畫回完整狀態。"
                        "請對破壞後的鏡頭停用該母版（改用文字描述或裁掉道具的母版），並在 metadata 設 scene_master_disabled=true 確認後即不再警告。")

    _NARRATOR_SPEAKERS = {"旁白", "narrator", "narration", "畫外音", "v.o.", "vo", "os", "o.s."}
    # Check 7c（#58）：同段多個說話人露臉 → 警告；使用者接受後設 metadata.accepted_mixed_face=true
    _spk = []
    for s in shots:
        _d = s.get("dialogue_and_audio") or {}
        _who = _d.get("speaker")
        # 旁白／畫外音沒有臉，不算露臉說話人
        if _who and (str(_who).strip().lower() in _NARRATOR_SPEAKERS or _d.get("audio_type") == "offscreen"):
            continue
        if _d.get("has_dialogue") and _who and _who not in _spk:
            _spk.append(_who)
    if len(_spk) > 1 and not (data.get("metadata") or {}).get("accepted_mixed_face"):
        warnings.append(f"[同段多說話人露臉] 本段有 {len(_spk)} 位說話人（{'、'.join(map(str, _spk))}）；H3 單段容易混臉。"
                        "建議拆段；若接受風險，在 metadata 設 accepted_mixed_face=true 即不再警告。")

    # Check 7b: 同段內跨鏡頭複製貼上檢查 (background_idle_life / micro_physics_tail / observable_expression)
    for field_key, field_label in (
        ("background_idle_life", "背景動態 (background_idle_life)"),
        ("micro_physics_tail", "微物理尾韻 (micro_physics_tail)"),
        ("observable_expression", "外顯表情 (observable_expression)"),
    ):
        seen_vals = {}
        for s in shots:
            sid = s.get("shot_id", "SH")
            val = (s.get("action_and_performance", {}).get(field_key) or "").strip()
            if val and len(val) >= 6:
                if val in seen_vals:
                    errors.append(
                        f"[{sid} 同段複製貼上偷懶違規] {field_label}「{val}」與同段鏡頭 {seen_vals[val]} 完全重複！"
                        f"請針對每一鏡的實際動作與光影獨立撰寫。"
                    )
                else:
                    seen_vals[val] = sid

    # 雙人引子（spatial-consistency.md §7）：組裝剪掉，說話佔比、段長提醒、9:16 景別比例都以成片（扣掉引子）計
    lead_in_s = dual_lead_in.lead_in_seconds(data) if len(shots) > 1 else 0.0
    film_dur = target_dur - lead_in_s if target_dur > 0 else target_dur
    film_shots = shots[1:] if lead_in_s else shots
    lead_note = f"（已扣雙人引子 {lead_in_s:g}s）" if lead_in_s else ""

    # 整段說話時長比例（v118 #5：#118 目標 75–90%，超過 90% 才提醒；依畫內 4.5／VO 5.5 字/秒估）
    total_speech_sec = 0.0
    for sh in shots:
        _d = sh.get("dialogue_and_audio", {}) or {}
        if _d.get("has_dialogue"):
            _rate = VO_RATE_WARN if is_voiceover_line(_d) else ONSCREEN_RATE_WARN
            total_speech_sec += sum(count_speech_chars(t) for t in shot_lines(_d)) / _rate
    if film_dur > 0 and (total_speech_sec / film_dur) > SPEECH_SHARE_WARN:
        warnings.append(
            f"⚠️ 說話佔比偏高：整段說話預估 {total_speech_sec:.1f}s / {film_dur:.1f}s{lead_note} = "
            f"{total_speech_sec / film_dur:.1%} > {SPEECH_SHARE_WARN:.0%}（目標 75–90%），檢查句間是否還有 0.1s 以上氣口。"
        )

    # 分段時長提醒（成片長度：雙人引子會剪掉，不算）
    if film_dur > 10.0 or film_dur < 5.0:
        warnings.append(
            f"[分段時長提醒] 本段時長 {round(film_dur, 3):g}s{lead_note}：每段建議 2–4 個節拍、7–10 秒（15 秒僅為 H3 單次上限而非硬規則），"
            f"且每段應為自足開場；收尾在最後一句說完後 0.3 秒（無廢片，不留靜止尾格）。"
        )
    checks_passed.append(
        "[分段時長設計建議] 每段建議 2–4 個節拍、7–10 秒（15 秒僅為 H3 單次上限而非硬規則），"
        "且每段應為自足開場；收尾在最後一句說完後 0.3 秒（無廢片，不留靜止尾格）。"
    )

    checks_passed.append("[PASS] 單鏡動作 <=5 階段、武戲 90° 防遮擋與遠景五官過濾核對完成")
    checks_passed.append("[PASS] 偽精確數值 (3mm/折射率)、萬用罐頭詞與醫學解剖肌群詞零殘留")

    # Check 8: 劇本台詞 100% 一字不差保真核對
    if original_script_dialogues is not None:
        dlg_errors = verbatim_check(original_script_dialogues, dialogue_stream([data]))
        if dlg_errors:
            errors += dlg_errors
        else:
            total_chars = count_speech_chars("".join(original_script_dialogues))
            checks_passed.append(f"[PASS] 台詞 100% 一字不差保真核對通過 (共 {total_chars} 字)")

    # Check 9: 9:16 豎屏短劇景別比例檢查
    if aspect == "9:16":
        cu_ratio = sum(1 for s in film_shots
                       if (s.get("camera_optics") or {}).get("shot_size", "MS") in ("MCU", "CU", "ECU", "OTS_CU")) / len(film_shots)
        if cu_ratio < 0.65:
            warnings.append(f"[9:16 豎屏構圖警告] 中近景/特寫佔比僅 {cu_ratio:.0%} (建議 >= 70%)，手機螢幕人物過小。")
        else:
            checks_passed.append(f"[PASS] 9:16 豎屏中近景/特寫高佔比核對通過 ({cu_ratio:.0%})")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks_passed": checks_passed
    }


def check_cross_segment_slop(datas: list) -> list:
    """跨分段批量複製貼上偵測：若同一句 background_idle_life / micro_physics_tail / observable_expression
    在多個分鏡檔中重複出現 >= 3 次，判定為腳本批量灌水造假並強制攔截。"""
    errors = []
    if len(datas) < 2:
        return errors
    errors += cross_segment_intent_errors(datas)
    for field_key, label in (
        ("background_idle_life", "background_idle_life"),
        ("micro_physics_tail", "micro_physics_tail"),
        ("observable_expression", "observable_expression"),
    ):
        counts: dict = {}
        for d in datas:
            seg_id = d.get("segment_id") or d.get("scene_id") or "SEG"
            for s in d.get("shots", []):
                val = (s.get("action_and_performance", {}).get(field_key) or "").strip()
                if val and len(val) >= 6:
                    counts.setdefault(val, []).append(f"{seg_id}:{s.get('shot_id', '')}")
        for val, locs in counts.items():
            if len(locs) >= 3:
                errors.append(
                    f"[跨段批量罐頭詞違規] `{label}` 內容「{val}」在全集重複出現 {len(locs)} 次 "
                    f"({', '.join(locs[:4])}...)！嚴禁用腳本批量塞罐頭句敷衍過檢！"
                )
    return errors



def run_demo_suite():
    print("=" * 78)
    print("🔍 啟動 cinematic-director-storyboard v2.0 靜態驗證與回歸測試套件 (Golden Suite)")
    print("=" * 78)

    # 測試案例 1：合規的實驗 A (深夜辦公室對峙 12s)
    valid_case = {
        "project_id": "TEST_A_OFFICE",
        "scene_id": "SC01",
        "segment_id": "SEG01",
        "metadata": {
            "aspect_ratio": "16:9",
            "target_duration_sec": 12.0,
            "pacing_profile": "Slow_Cinematic",
            "density_exempt_reason": "對峙靜場示範：沉默本身是戲，台詞刻意稀疏",
            "lighting_lock_line": "冷鋼夜黑 (#0A0E17 暗部 + 4500K 窗外冷藍側逆光 + #D4AF37 門縫暖光)"
        },
        "continuity_handshake": {"mode": "HARD_CUT_ESTABLISH", "overflow_dialogue_out": None},
        "shots": [
            {
                "shot_id": "SH01", "start_time": 0.0, "end_time": 3.0, "duration": 3.0,
                "dramatic_beat_type": "Expository_Fast",
                "camera_optics": {"shot_size": "MLS", "focal_length": "35mm", "physical_distance": "2.0m", "pov_routing": "objective", "movement": "Rack Focus"},
                "spatial_blocking": {"anchor_objects": ["落地玻璃窗", "深色實木門"], "blocking_desc": "左A背影，右B推門"},
                "action_and_performance": {"action_stages": ["A靜立窗前", "B推門走入", "焦點由A移至B"], "observable_expression": "A背影沉穩，B神情戒備"},
                "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
            },
            {
                "shot_id": "SH02", "start_time": 3.0, "end_time": 6.5, "duration": 3.5,
                "dramatic_beat_type": "Dramatic_Core",
                "camera_optics": {"shot_size": "CU", "focal_length": "85mm", "physical_distance": "3.5m", "pov_routing": "objective", "movement": "Slow Dolly-in"},
                "spatial_blocking": {"anchor_objects": ["落地玻璃窗"], "blocking_desc": "A側臉近景"},
                "action_and_performance": {"action_stages": ["A不回頭凝視窗玻璃倒影", "喉結微滾低聲開口", "尾字下頜微繃"], "observable_expression": "眼簾微垂，眼神冷峻"},
                "dialogue_and_audio": {"has_dialogue": True, "speaker": "A", "line_verbatim": "你終於來了。", "lips_closed_lock": False}
            },
            {
                "shot_id": "SH03", "start_time": 6.5, "end_time": 9.0, "duration": 2.5,
                "dramatic_beat_type": "Suspense_Delay",
                "camera_optics": {"shot_size": "ECU", "focal_length": "85mm", "physical_distance": "1.5m", "pov_routing": "objective", "movement": "Tilt Up"},
                "spatial_blocking": {"anchor_objects": ["紅木辦公桌", "白色信封"], "blocking_desc": "B停步於桌角"},
                "action_and_performance": {"action_stages": ["B雙腳急停", "五指猛然收緊捏皺白色信封"], "observable_expression": "指節用力泛白，紙張折痕明顯"},
                "dialogue_and_audio": {"has_dialogue": False, "lips_closed_lock": True}
            },
            {
                "shot_id": "SH04", "start_time": 9.0, "end_time": 12.0, "duration": 3.0,
                "dramatic_beat_type": "Reaction_OTS",
                "camera_optics": {"shot_size": "OTS_CU", "focal_length": "100mm", "physical_distance": "6.0m", "pov_routing": "defensive_reaction_ots", "movement": "Static"},
                "spatial_blocking": {"anchor_objects": ["紅木辦公桌"], "blocking_desc": "越過A暗部右肩拍B"},
                "action_and_performance": {"action_stages": ["B抬眼望向A背影", "雙唇微顫開口回答", "眼簾垂落輕嘆"], "observable_expression": "眼眶微紅，下唇微顫"},
                "dialogue_and_audio": {"has_dialogue": True, "speaker": "B", "line_verbatim": "我不該來的。", "lips_closed_lock": False}
            }
        ],
        "segment_end_state": {"planned_final_state": {"envelope": "creased"}, "observed_final_state": None}
    }


    # 每鏡先寫鏡頭意圖，再為技術選擇寫理由（references/storyboard/shot-intent.md）
    _intents = [
        ({"audience": "A 早就在等 B，B 一進門就落入 A 的地盤", "story_beat": "B 赴約進門，兩人第一次同處一室",
          "pov": "旁觀者，同時看見兩人", "emotional_shift": "安靜等待轉成戒備對峙"},
         {"shot_size": "MLS 才能同時框進窗前的 A 與門口的 B，交代兩人距離", "lens_distance": "35mm 2 公尺接近人眼，不偏袒任何一方",
          "movement": "焦點由 A 移到 B，代替切鏡把注意力交給剛進門的人", "blocking": "A 背對鏡頭在左、B 在右門口，背對的 A 顯得從容",
          "background": "落地窗冷光與門縫暖光同框，冷暖分別屬於 A 與 B"}),
        ({"audience": "A 不必回頭就掌握了 B，台詞是宣告而不是寒暄", "story_beat": "A 先開口定調",
          "pov": "貼近 A，觀眾和 A 一起看玻璃倒影", "emotional_shift": "沉默轉成壓迫"},
         {"shot_size": "CU 讓觀眾讀到 A 眼簾下垂與下頜收緊", "lens_distance": "85mm 3.5 公尺壓扁背景，窗上倒影貼在 A 臉旁",
          "movement": "慢推在台詞前完成，推近的壓力落在第一個字上", "blocking": "A 側臉在畫左三分之一，視線朝畫右看玻璃裡的 B",
          "background": "只留窗玻璃與 B 的模糊倒影，提醒 B 就在身後", "line_timing": "推鏡停住後 0.5 秒才開口，讓台詞在靜止畫面裡落地"}),
        ({"audience": "B 被那句話刺中，手比臉先洩漏情緒", "story_beat": "B 的反應：信封被捏皺",
          "pov": "B 自己都沒察覺的身體反應，觀眾比 A 先看到", "emotional_shift": "強裝鎮定轉成失控"},
         {"shot_size": "ECU 只拍手與信封，表情交給動作", "lens_distance": "85mm 1.5 公尺讓指節和紙紋清楚可讀",
          "movement": "從停下的腳搖到手，跟著緊張往上爬", "blocking": "B 停在桌角，手在畫面中央下方，信封白色面朝鏡頭",
          "background": "紅木桌面暗沉，襯出白信封與發白指節"}),
        ({"audience": "B 想退卻，A 的背影仍佔著畫面一角", "story_beat": "B 回答，落下本段結尾",
          "pov": "站在 A 身後看 B，觀眾與 A 同一陣線", "emotional_shift": "失控收成無力的後悔"},
         {"shot_size": "OTS_CU 讓 A 的肩擋住一角，B 被夾在 A 的陰影裡", "lens_distance": "100mm 6 公尺壓縮兩人距離，B 無處可退",
          "movement": "固定，讓 B 下唇的顫動成為畫面唯一的動", "blocking": "A 暗部右肩在畫左前景虛焦，B 在畫右三分之一抬眼看 A",
          "background": "門縫暖光在 B 身後，是她進來的路，也是退路", "line_timing": "抬眼後才開口，說完垂眼嘆氣做收尾停格"}),
    ]
    for _shot, (_intent, _why) in zip(valid_case["shots"], _intents):
        _shot["shot_intent"], _shot["choice_why"] = _intent, _why

    res1 = validate_storyboard_data(valid_case, original_script_dialogues=["你終於來了。", "我不該來的。"])
    print("\n✅ [測試 1：標準合規分鏡 (實驗 A 辦公室對峙)] 審查結果:", "PASS" if res1["passed"] else "FAIL")
    for p in res1["checks_passed"]:
        print("  ", p)

    # 測試案例 2：故意注入野生提示詞常見病灶 (禁光影、眼輪匝肌、3mm、武戲用Dirty Frame遮擋、遠景寫瞳孔、竄改台詞)
    flawed_case = {
        "project_id": "TEST_FLAWED",
        "scene_id": "SC02",
        "segment_id": "SEG01",
        "metadata": {"aspect_ratio": "16:9", "target_duration_sec": 10.0, "pacing_profile": "Fast_ShortDrama", "lighting_lock_line": ""},
        "continuity_handshake": {"mode": "SEAMLESS_CONTINUATION"},
        "shots": [
            {
                "shot_id": "SH01_BAD", "start_time": 0.0, "end_time": 4.0, "duration": 4.0,
                "dramatic_beat_type": "Combat_Impact",
                "camera_optics": {"shot_size": "ELS", "focal_length": "24mm", "physical_distance": "<0.4m", "pov_routing": "dirty_frame_20_35", "movement": "Pan"},
                "spatial_blocking": {"anchor_objects": ["盾牌"], "blocking_desc": "A擊中B盾牌"},
                "action_and_performance": {
                    "action_stages": ["s1", "s2", "s3", "s4", "s5", "s6_overflow"],
                    "observable_expression": "遠景中A眼輪匝肌收縮，嘴角下垂3mm，瞳孔驟然放大"
                },
                "dialogue_and_audio": {"has_dialogue": True, "speaker": "A", "line_verbatim": "你終於來啦！", "lips_closed_lock": False}
            }
        ],
        "segment_end_state": {"planned_final_state": {}}
    }

    res2 = validate_storyboard_data(flawed_case, original_script_dialogues=["你終於來了。"])
    print("\n🛡️ [測試 2：病態提示詞防呆攔截測試 (故意注入 6 項違規)] 審查結果:", "成功攔截所有違規!" if not res2["passed"] else "未攔截")
    for err in res2["errors"]:
        print("   ❌ 攔截成功 ->", err)
    print("=" * 78)


def check_dialogue_groups(datas: list, handoff: dict, only_scene: str = None) -> dict:
    """同一場景的各段依段序串接台詞，與 handoff 劇本台詞比對。回傳 {scene_id: {passed, errors, segments}}。"""
    expected_map = load_handoff_dialogues(handoff)
    mark_map = {sc.get("scene_id"): action_marks.expected_marks(sc)
                for ep in handoff.get("episodes", []) for sc in ep.get("scenes", [])}
    groups: dict = {}
    for data in datas:
        groups.setdefault(scene_key(data), []).append(data)
    results = {}
    for scene_id in [only_scene] if only_scene else list(groups):
        segs = sorted(groups.get(scene_id, []),
                      key=lambda d: segment_sort_key(d.get("segment_id", d.get("scene_id", ""))))
        if scene_id not in expected_map:
            errors = [f"[台詞保真] handoff 內找不到場景 {scene_id}"]
        elif not segs:
            errors = [f"[台詞保真] 找不到場景 {scene_id} 的分鏡檔，無法核對台詞"]
        else:
            errors = verbatim_check(expected_map[scene_id], dialogue_stream(segs)) + jcut_errors(segs)
            errors += action_marks.scene_count_errors(scene_id, mark_map.get(scene_id, []), segs)  # D5 標記數
        results[scene_id] = {
            "passed": not errors,
            "errors": errors,
            "segments": [d.get("segment_id", d.get("scene_id")) for d in segs],
        }
    return results


def load_json(path: str):
    """讀取 JSON；任何讀檔或解析失敗都拋出 ValueError，訊息帶檔名與位置。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as exc:
        raise ValueError(f"{path} 讀取失敗：{exc.strerror or exc}") from None
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} 不是 UTF-8 編碼：{exc.reason}") from None
    if not text.strip():
        raise ValueError(f"{path} 是空檔案")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} 不是合法 JSON（第 {exc.lineno} 行第 {exc.colno} 欄）：{exc.msg}") from None


# 6d 的舊預設名單（《噩盡島》與早期範例）；新專案不需要它，名單改從 Layer 2 讀（見 _segment_anchor_names）。
LEGACY_ANCHORED_NAMES = ("洛年", "沈洛年", "懷真", "賴一心", "瑪蓮", "奇雅", "狄純", "巨鼠", "巨蟒", "白獸",
                         "調查員", "旅人", "女主角", "劍客")
# 範例裡的「角色 A／B」：只認獨立字母，不再用子字串（舊寫法會讓任何含大寫 A／B 的文字都算已錨定）
_PLACEHOLDER_ROLE_RE = re.compile(r"(?<![A-Za-z])[AB](?![A-Za-z])")


def _segment_anchor_names(data: dict) -> list:
    """本段登記的角色名：asset_refs.characters[].name／name_zh／display_name 與 metadata.anchored_names。"""
    names: list = []
    for entry in ((data.get("asset_refs") or {}).get("characters") or []):
        if isinstance(entry, dict):
            names.extend(str(entry[k]) for k in ("name", "name_zh", "display_name") if entry.get(k))
    extra = (data.get("metadata") or {}).get("anchored_names") or []
    names.extend(str(x) for x in (extra if isinstance(extra, list) else [extra]) if x)
    return names


def find_project_root(path) -> "Path | None":
    """從 layer2 檔往上找專案根目錄（有 adapt/bible.json、assets/character-packs.json 或 assets.md）。"""
    p = Path(path).resolve()
    for cand in [p.parent, *p.parents][:4]:
        if (cand / "adapt" / "bible.json").is_file() or (cand / "assets" / "character-packs.json").is_file() \
                or (cand / "assets.md").is_file():
            return cand
    return None


def load_reference_ids(root) -> tuple:
    """(ref_ids, voice_only_ids)：有參考包或設定圖的角色、只聞其聲的角色。找不到任何角色表回 (None, set())。

    參考來源：assets/character-packs.json 的 packs、bible.json 角色的 reference_image／image_path／ref_img、
    assets.md `### <ID>` 區塊裡的 images/*.png、images/ref/<id>_front.png（Codex 構圖用的正面裁切）。"""
    if root is None:
        return None, set()
    root = Path(root)
    ref_ids, voice_only, found = set(), set(), False
    packs_path = root / "assets" / "character-packs.json"
    if packs_path.is_file():
        found = True
        try:
            packs = json.loads(packs_path.read_text(encoding="utf-8-sig")).get("packs") or {}
        except (OSError, ValueError, AttributeError):
            packs = {}
        for pid, rec in (packs.items() if isinstance(packs, dict) else []):
            if isinstance(rec, dict) and (rec.get("voice_only") or rec.get("no_visual_reference")):
                voice_only.add(str(pid))
            else:
                ref_ids.add(str(pid))
    bible_path = root / "adapt" / "bible.json"
    if bible_path.is_file():
        found = True
        try:
            bible = json.loads(bible_path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            bible = {}
        chars = bible.get("characters") or [] if isinstance(bible, dict) else []
        for rec in (chars.values() if isinstance(chars, dict) else chars):
            if not isinstance(rec, dict):
                continue
            cid = str(rec.get("id") or rec.get("character_id") or "")
            if not cid:
                continue
            if rec.get("voice_only") or rec.get("no_visual_reference"):
                voice_only.add(cid)
            if any(rec.get(k) for k in ("reference_image", "image_path", "ref_img")):
                ref_ids.add(cid)
    assets_md = root / "assets.md"
    if assets_md.is_file():
        found = True
        for m in re.finditer(r"^###\s+([A-Z]+-[A-Za-z0-9_-]+)(.*?)(?=^#{2,3}\s|\Z)",
                             assets_md.read_text(encoding="utf-8"), re.M | re.S):
            if re.search(r"images/[A-Za-z0-9_./-]+\.png", m.group(2)):
                ref_ids.add(m.group(1))
    ref_dir = root / "images" / "ref"
    if ref_dir.is_dir():
        ref_ids.update(p.name[:-len("_front.png")] for p in ref_dir.glob("*_front.png"))
    return (ref_ids if found else None), voice_only


def check_segment_seams(datas: list) -> list:
    """D05：同一場景相鄰兩段（依段序）的接縫提醒；只警告、不影響 passed。"""
    by_scene: dict = {}
    for d in datas:
        if isinstance(d, dict) and d.get("shots"):
            by_scene.setdefault(str(d.get("scene_id") or ""), []).append(d)
    out = []
    for scene, segs in by_scene.items():
        segs = sorted(segs, key=lambda d: segment_sort_key(str(d.get("segment_id") or "")))
        for prev, nxt in zip(segs, segs[1:]):
            for msg in lint_segment_seam((prev.get("shots") or [None])[-1], (nxt.get("shots") or [None])[0]):
                out.append(f"{prev.get('segment_id')}→{nxt.get('segment_id')}：{msg}")
    return out


def main():
    parser = argparse.ArgumentParser(description="AI 電影與漫劇分鏡靜態驗證器 (v2.0)")
    parser.add_argument("--file", nargs="+", help="待驗證的 Layer 2 JSON 分鏡檔（一或多個；分段時請把各段一併給出）")
    parser.add_argument("--handoff", nargs="+",
                        help="handoff JSON（多集專案可給多個或萬用字元，如 handoff-ep*.json）；提供時核對各場景台詞與劇本逐字一致（段落自動依段序合併）")
    parser.add_argument("--scene", help="搭配 --handoff，只核對指定場景，例如 EP01-S01")
    parser.add_argument("--demo", action="store_true", help="執行內建合規與防呆攔截雙向回歸測試")
    parser.add_argument("--root", help="專案根目錄（6e 讀角色包／設定圖清單）；不給時從第一個 layer2 檔往上找")
    args = parser.parse_args()

    if args.demo or not args.file:
        run_demo_suite()
        return
    if args.scene and not args.handoff:
        parser.error("--scene 需要搭配 --handoff")

    expanded_files = []
    import glob
    for p in args.file:
        if any(c in p for c in ("*", "?", "[")):
            matched = sorted(glob.glob(p))
            expanded_files.extend(matched if matched else [p])
        elif Path(p).is_dir():
            matched = sorted(glob.glob(os.path.join(p, "layer2-*.json")))
            expanded_files.extend(matched if matched else [p])
        else:
            expanded_files.append(p)
    args.file = expanded_files

    handoff_paths = []
    for p in args.handoff or []:
        matched = sorted(glob.glob(p)) if any(c in p for c in ("*", "?", "[")) else []
        handoff_paths.extend(matched or [p])
    try:
        datas = [load_json(path) for path in args.file]
        handoffs = [(path, load_json(path)) for path in handoff_paths]
    except ValueError as exc:
        print(f"[錯誤] {exc}", file=sys.stderr)
        sys.exit(1)

    problems = [f"{path}：{msg}" for path, data in zip(args.file, datas) for msg in layer2_format_errors(data)]
    for path, item in handoffs:
        problems += [f"{path}：{msg}" for msg in handoff_format_errors(item)]
    handoff = None
    if handoffs and not problems:
        # 多集：逐集 handoff 的 episodes 串起來，一次比對全部段落（單一 handoff 時行為不變）
        handoff = dict(handoffs[0][1])
        handoff["episodes"] = [ep for _, item in handoffs for ep in item.get("episodes", [])]
    if problems:
        for msg in problems:
            print(f"[錯誤] {msg}", file=sys.stderr)
        sys.exit(1)

    try:
        root = args.root or (find_project_root(args.file[0]) if args.file else None)
        ref_ids, voice_only_ids = load_reference_ids(root)
        files = {path: validate_storyboard_data(data, ref_ids=ref_ids, voice_only_ids=voice_only_ids)
                 for path, data in zip(args.file, datas)}
        dialogue = check_dialogue_groups(datas, handoff, args.scene) if handoff is not None else {}
        cross_slop = check_cross_segment_slop(datas)
    except Exception as exc:  # 最後防線：未預期的資料異常只印錯誤訊息，不噴 traceback
        print(f"[錯誤] 驗證時遇到無法處理的資料：{exc}", file=sys.stderr)
        sys.exit(1)

    if handoff is None and len(args.file) == 1:
        res = next(iter(files.values()))
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0 if res["passed"] else 1)

    passed = all(r["passed"] for r in files.values()) and all(r["passed"] for r in dialogue.values()) and not cross_slop
    out_obj = {"passed": passed, "files": files, "dialogue_checks": dialogue}
    seams = check_segment_seams(datas)
    if seams:
        out_obj["seam_warnings"] = seams
    if cross_slop:
        out_obj["cross_segment_slop_errors"] = cross_slop
    print(json.dumps(out_obj, ensure_ascii=False, indent=2))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

