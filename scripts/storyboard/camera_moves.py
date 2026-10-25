"""PR-14b：運鏡預設庫。Layer 2 camera_optics.move_preset 指名一個預設，編譯器展開成完整 Camera 子句。

句型來自 Colab 實測（第 1、2 輪）；status 為驗證狀態：pass／experimental（偏弱）。
slots：必填槽位，來自 camera_optics.move_slots（物件）。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

PRESETS: Dict[str, dict] = {
    "dutch_canted": {
        "aliases": ["dutch", "dutch angle", "荷蘭角", "斜角"],
        "slots": [],
        "status": "pass",
        "strong": False,
        "clause": ("a canted frame held from the first frame to the last: every vertical line in the picture "
                   "leans about 30 degrees to the left and the ground line slopes steeply, like a crooked printed photo; "
                   "the camera does not roll, tilt back or level out"),
        "note": "只寫 tilt 角度會被忽略，要描述畫面結果。",
    },
    "top_down_rise": {
        "aliases": ["top down rise", "overhead rise", "頂拍上升", "純垂直俯拍"],
        "slots": [],
        "status": "pass",
        "strong": True,
        "clause": ("a top-down shot with the lens pointing straight down for the whole shot while the camera pedestals "
                   "straight up; the horizon never appears and the camera does not tilt or pan"),
        "note": "全程朝下，禁止漸變成斜俯。",
    },
    "high_angle_tilt_down": {
        "aliases": ["high angle tilt", "俯搖", "高角度俯搖"],
        "slots": ["target"],
        "status": "pass",
        "strong": False,
        "clause": "starts from a high angle and tilts down until {target} fills the lower center of the frame",
        "note": "tilt down 要給落點物件。",
    },
    "bullet_time": {
        "aliases": ["bullet time", "子彈時間", "凍結環繞"],
        "slots": ["subject"],
        "status": "pass",
        "strong": True,
        "clause": ("time is already completely frozen from the first frame, hair, cloth, dust and debris hang motionless, "
                   "{subject} does not blink or breathe; only the camera moves, trucking left at fast speed while panning "
                   "right to keep {subject} centered, circling a full 360 degrees at a constant distance"),
        "note": "需完整場景段、不用參考圖背景；仙俠版身份優先、明寫髮長；凍結需後製確認。",
    },
    "dolly_zoom": {
        "aliases": ["dolly zoom", "推拉變焦", "vertigo"],
        "slots": ["subject"],
        "status": "experimental",
        "strong": True,
        "clause": ("zooms out while the camera pushes in toward {subject}, so {subject} stays the same size "
                   "while the background stretches away"),
        "note": "實驗性（偏弱）；pull out＋zoom in 無效。",
    },
    "ots_reveal": {
        "aliases": ["ots", "over the shoulder", "過肩", "揭示"],
        "slots": ["foreground", "subject"],
        "status": "pass",
        "strong": False,
        "clause": ("an over-the-shoulder view past {foreground} in the foreground, then the camera slowly pushes in toward "
                   "{subject}; everyone keeps the clothing shown in their reference"),
        "note": "補場景、重申參考服裝，否則會換衣。",
    },
}


def _norm(s: str) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def find_preset(name: str) -> str:
    """名稱或別名 → preset id；找不到回傳空字串。"""
    key = _norm(name)
    for pid, spec in PRESETS.items():
        if key == pid or key in {_norm(a) for a in spec["aliases"]}:
            return pid
    return ""


def expand_preset(name: str, slots: Optional[dict] = None) -> Tuple[str, List[str]]:
    """回傳（Camera 子句, 警告）。未知預設或缺槽位 → ValueError。"""
    pid = find_preset(name)
    if not pid:
        raise ValueError(f"未知的 move_preset: {name!r}；可用：{', '.join(sorted(PRESETS))}")
    spec = PRESETS[pid]
    slots = {k: str(v).strip() for k, v in (slots or {}).items() if str(v or "").strip()}
    missing = [k for k in spec["slots"] if k not in slots]
    if missing:
        raise ValueError(f"move_preset {pid} 缺必填槽位 {missing}（camera_optics.move_slots）")
    warnings = []
    if spec["status"] != "pass":
        warnings.append(f"move_preset {pid} 為{spec['status']}：{spec['note']}")
    return spec["clause"].format(**slots), warnings
