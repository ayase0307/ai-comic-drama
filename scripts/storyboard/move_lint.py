# -*- coding: utf-8 -*-
"""PR-14c：運鏡導演助手與 lint（階段 4，全部是 warning，實測後再升 strict）。

lint_segment_moves(shots)：同段多個強運鏡、對白鏡用強運鏡、連續同運鏡、≤2 秒子鏡用強運鏡、
  slots 缺漏、OTS 前景未綁圖、子彈時間主體未錨定、FPV 無人物仍掛參考圖等。
recommend_move(intent_text, ...)：依 shot_intent 文字（audience／story_beat／emotional_shift）推薦首選／備選運鏡。
"""
from __future__ import annotations

import re
from typing import Dict, List

try:
    import camera_moves
except ImportError:  # 以套件載入
    from . import camera_moves

STRONG_PER_SEGMENT = 2
MIN_STRONG_SECONDS = 2.5

# 場景意圖關鍵字 → (首選, 備選, 理由)。只用已 Colab 驗證 pass 的預設。
INTENT_RULES = [
    (r"震驚|頓悟|意識到|驚覺|realiz|shock", ("dolly_zoom", ["eyes_in"], "主角不動、世界變形＝內心衝擊")),
    (r"孤立|渺小|孤獨|lonely|isolat", ("aerial_pullback", ["dutch_canted"], "主角縮成小點＝被世界吞沒")),
    (r"失衡|不安|詭異|不對勁|unease|off-kilter", ("dutch_canted", [], "固定斜角維持失衡感，不要漸變")),
    (r"揭露|揭示|reveal|登場", ("ots_reveal", ["super_dolly_in"], "前景遮擋後推近揭示")),
    (r"凝視|眼神|決心|resolve", ("eyes_in", ["snorricam"], "推到眼睛＝進入內心")),
    (r"追逐|衝向|逼近|charge|rush", ("super_dolly_in", ["snorricam"], "長軌衝推製造速度")),
    (r"高潮|定格|凍結|最強一擊|climax|freeze", ("bullet_time", [], "子彈時間；定格需後製確認")),
    (r"俯瞰|全景|建立|開場|establish", ("top_down_rise", ["aerial_pullback"], "俯拍建立地理")),
    (r"回憶|往事|平行|同時|simultaneous|flashback", ("split_screen_3", [], "同一瞬間多角度／多地點")),
    (r"暈眩|失控|dizz|vertigo", ("snorricam", ["dolly_zoom"], "綁身鏡頭讓背景晃動")),
    (r"急推|恍然大悟|笑點|crash", ("crash_zoom", ["push_in"], "半秒急推強調；機位不動")),
    (r"甩鏡|甩向|猛地看|whip", ("whip_pan", ["foreground_wipe"], "單次甩鏡，末端急停")),
    (r"轉焦|焦點轉|rack focus", ("rack_focus", [], "固定機位、淺景深轉焦")),
    (r"權力|威脅|英雄|霸氣|仰視|low.?angle", ("low_angle", ["static_hold"], "低機位仰角，不疊廣角")),
    (r"細節|微距|特寫物|macro", ("macro_push", ["push_in"], "單一小物件、寫焦點落點")),
    (r"升起|揭示全貌|史詩|rise.?orbit", ("aerial_reveal", ["rise_orbit"], "從遮擋物後升起再揭示")),
    (r"走進|穿過走廊|沉浸|steadicam", ("steadicam", ["follow"], "一個連續空間內穩定跟走")),
    (r"第一人稱|主觀|驚嚇|\bpov\b", ("pov", [], "只露手或工具，不露臉")),
    (r"遮擋轉場|藏接縫|前景遮擋轉|wipe", ("foreground_wipe", ["whip_pan"], "大面積實體完全遮滿")),
    (r"收緊|逼近一個|緊張|push.?in", ("push_in", [], "景別降一級慢推")),
    (r"跟拍|並行|行走對話|follow", ("follow", ["truck"], "主體比例不變")),
]
_DIALOGUE_AVOID = "對白鏡不該用強運鏡（CU／MCU 固定機位較穩）"


def recommend_move(text: str) -> Dict[str, object]:
    """回傳 {primary, alternates, why}；無匹配回傳空 dict（維持固定鏡頭）。"""
    for pat, (primary, alts, why) in INTENT_RULES:
        if re.search(pat, text or "", re.IGNORECASE):
            return {"primary": primary, "alternates": list(alts), "why": why}
    return {}


def _has_dialogue(shot: dict) -> bool:
    da = shot.get("dialogue_and_audio") or {}
    return bool(da.get("dialogue") or da.get("lines") or da.get("dialogue_en"))


def lint_segment_moves(shots: List[dict]) -> List[str]:
    out: List[str] = []
    strong: List[str] = []
    prev = ""
    for idx, s in enumerate(shots, 1):
        sid = s.get("shot_id", f"SH{idx:02d}")
        cam = s.get("camera_optics") or {}
        name = cam.get("move_preset")
        if not name:
            prev = ""
            intent = s.get("shot_intent") or {}
            text = " ".join(str(intent.get(k, "")) for k in ("audience", "story_beat", "emotional_shift"))
            rec = recommend_move(text)
            if rec and rec['primary'] in camera_moves.PRESETS and not _has_dialogue(s) and not cam.get("move_preset") \
                    and str(cam.get("movement", "static")).strip().lower() in ("static", "固定", "", "fixed"):
                out.append(f"[{sid} 運鏡建議] 依 shot_intent 建議 move_preset={rec['primary']}"
                           f"（備選 {'、'.join(rec['alternates']) or '無'}）：{rec['why']}；不用請忽略")
            continue
        pid = camera_moves.find_preset(name)
        if not pid:
            out.append(f"[{sid} move_preset 未知] {name!r} 不在預設庫；可用：{', '.join(sorted(camera_moves.PRESETS))}")
            continue
        spec = camera_moves.PRESETS[pid]
        slots = cam.get("move_slots") or {}
        missing = [k for k in spec["slots"] if not str(slots.get(k, "")).strip()]
        if missing:
            out.append(f"[{sid} move_slots 缺漏] {pid} 缺 {missing}")
        if spec.get("strong"):
            strong.append(sid)
            try:
                dur = float(s.get("duration") or 0)
            except (TypeError, ValueError):
                dur = 0
            if _has_dialogue(s):
                out.append(f"[{sid} 對白鏡用強運鏡] {_DIALOGUE_AVOID}")
            if dur and dur < MIN_STRONG_SECONDS:
                out.append(f"[{sid} 子鏡過短] {pid} 在 {dur:g} 秒內放不下，強運鏡至少 {MIN_STRONG_SECONDS:g} 秒（Colab 結論套短子鏡可信度減半）")
        if pid == "bullet_time" and not str(slots.get("subject", "")).strip():
            out.append(f"[{sid} 子彈時間主體未錨定] bullet_time 需 subject 槽位並明寫髮長／服裝")
        if pid == "ots_reveal" and slots.get("foreground") and not (s.get("asset_refs") or {}).get("foreground_ref") \
                and "無名" not in str(slots.get("foreground")) and "unnamed" not in str(slots.get("foreground")).lower():
            out.append(f"[{sid} OTS 前景人未綁圖] foreground 要綁參考圖，或標明「無名／unnamed」")
        if pid == prev:
            out.append(f"[{sid} 連續同運鏡] 與上一鏡同為 {pid}，節奏重複")
        prev = pid
    if len(strong) > STRONG_PER_SEGMENT:
        out.append(f"[同段多個強運鏡] 本段 {len(strong)} 鏡用強運鏡（{'、'.join(strong)}），一段最多 {STRONG_PER_SEGMENT} 個")
    return out
