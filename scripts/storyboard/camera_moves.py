"""PR-14b：運鏡預設庫。Layer 2 camera_optics.move_preset 指名一個預設，編譯器展開成完整 Camera 子句。

句型來自 Colab 實測（第 1、2、3 輪）；status 為驗證狀態：pass／experimental（偏弱）。
slots：必填槽位，來自 camera_optics.move_slots（物件）。
optional：選填槽位與預設值（同樣放在 move_slots）。
第 3 輪（PR-14 後續）加入 Loop Forge 配方（loopforge0/minimaxh3-shots-skills，MIT）：
dolly zoom 正／反向、snorricam、eyes-in、aerial pullback、super dolly in、yo-yo zoom、三格分割。
槽位設計參考 LF scene JSON：direction（方向）、subject_kind（person/animal/bird/object）、空間槽位
（space／near_objects／further_objects／ground）。
min_seconds：最短秒數；不足時 expand_preset 給警告，required_seconds() 回傳該升到的後端秒數。
framing：開場構圖建議；shot_sizes：與之相符的景別代碼，不符時警告。
no_bg_plate：不要掛背景參考圖（LF 實測：背景參考圖讓運鏡幅度砍半）。
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
    "handheld": {
        "aliases": ["handheld", "手持", "手持晃動"],
        "slots": [],
        "status": "experimental",
        "strong": False,
        "clause": ("handheld camera with continuous small shaky drift: the frame sways and jitters a few percent of its "
                   "width, the horizon and the background slide visibly against the subject on every beat, never locked off"),
        "note": "噩盡島實測：只寫 handheld 背景位移 0.12 px、比鎖死鏡還穩；必須描述畫面結果（背景相對主體持續位移），且包裝層不可同時含 static／locked off。",
        "caution": "此預設不可與固定機位（static／locked off）包裝句並用；首次生成請檢查背景位移",
    },
    "tilt_up_locked": {
        "aliases": ["tilt up", "仰搖", "仰搖鎖終幅", "低角度仰搖"],
        "slots": ["target"],
        "status": "experimental",
        "strong": False,
        "clause": ("starts on the lower part of the scene and tilts up smoothly from the first frame until {target} fills the "
                   "upper center of the frame; the shot size stays the same throughout, the camera does not pull back, "
                   "and {target} stays fully inside the frame at the end"),
        "note": "噩盡島實測：仰搖終幅被拉成全身遠景、目標出畫；要給落點物件並鎖定景別不變。",
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
        "aliases": ["dolly zoom", "推拉變焦", "滑動變焦", "vertigo", "dolly zoom 正向", "dolly_zoom_forward",
                    "推拉變焦正向", "滑動變焦正向", "希區考克變焦"],
        "slots": ["subject", "background"],
        "optional": {"direction": "forward"},
        "direction_variants": {"reverse": "dolly_zoom_reverse", "telephoto": "dolly_zoom_reverse",
                               "反向": "dolly_zoom_reverse"},
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "開場即終景（腰上中近景）；不要從遠景開，否則變普通推近",
        "shot_sizes": ["MCU", "MS", "CU"],
        "clause": ("{subject}'s size and position in frame stay exactly constant throughout the entire shot, framed "
                   "identically in the last frame as in the first, neither closer nor further away, never drifting from "
                   "the centre of frame; {subject} faces the camera squarely for the whole shot and never turns away, "
                   "standing rooted to one spot without stepping, leaning or shifting weight; the camera pushes in while "
                   "simultaneously zooming out at exactly the matching rate, so that the size of {subject} in frame is "
                   "cancelled out entirely and does not change, while {background} behind recede, shrink, and spread "
                   "apart into much greater depth as the lens's focal length changes; only the background transforms"),
        "note": ("第 3 輪 LF 句型驗證可用：先鎖主角大小位置＋面向鏡頭＋站定，再寫 push in＋zoom out；"
                 "background 要寫建物結構（樓群、水塔、圍籬）；不加背景參考圖。"),
    },
    "dolly_zoom_reverse": {
        "aliases": ["dolly zoom reverse", "reverse dolly zoom", "dolly zoom telephoto", "dolly zoom 反向",
                    "推拉變焦反向", "滑動變焦反向", "反向推拉變焦"],
        "slots": ["subject", "background"],
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "開場即終景（腰上中近景）",
        "shot_sizes": ["MCU", "MS", "CU"],
        "clause": ("{subject}'s size and position in frame stay exactly constant throughout the entire shot, framed "
                   "identically in the last frame as in the first, neither closer nor further away, never drifting from "
                   "the centre of frame; {subject} faces the camera squarely for the whole shot and never turns away, "
                   "standing rooted to one spot without stepping, leaning or shifting weight; the camera pulls out while "
                   "simultaneously zooming in at exactly the matching rate, so that the size of {subject} in frame is "
                   "cancelled out entirely and does not change, while {background} behind flatten, grow, and compress "
                   "closer together as the lens's focal length changes; only the background transforms"),
        "note": "第 3 輪驗證：pull out＋zoom in，背景放大壓近（第 2 輪舊寫法失敗）。",
    },
    "snorricam": {
        "aliases": ["snorricam", "snorricam shot", "身綁鏡頭", "綁身鏡頭", "胸掛鏡頭"],
        "slots": ["subject"],
        "optional": {"stride": "with every stride"},
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "腰上中近景，主角自己往前走",
        "shot_sizes": ["MCU", "MS", "CU"],
        "moving_subject": True,
        "clause": ("{subject} walks steadily forward while the camera, fixed rigidly to {subject}, holds {face} locked "
                   "dead-centre at exactly the same size and position throughout; the whole background lurches, sways "
                   "and swings behind {subject} {stride}"),
        "note": ("第 3 輪驗證（晃動偏溫和）；主角必須自己移動，表演寫 eyes locked forward、never looking at the camera，"
                 "不要加轉身；不要在器材描述寫 body rig。"),
    },
    "eyes_in": {
        "aliases": ["eyes in", "eyes-in", "推進眼睛", "推到眼睛", "穿眼推進"],
        "slots": ["subject"],
        "optional": {"eye": "right"},
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "腰上中近景開場，一路推到眼睛",
        "shot_sizes": ["MCU", "MS", "MLS"],
        "clause": ("the camera pushes in with large amplitude at slow speed toward {face} and keeps going past it until "
                   "{detail} fills the entire frame edge to edge"),
        "note": "第 3 輪驗證：全身→中景→特寫→落在眼睛，連續無跳切；非人物主體要給 detail 槽位。",
    },
    "aerial_pullback": {
        "aliases": ["aerial pullback", "aerial pull back", "高空後拉", "空拍後拉", "升空後拉"],
        "slots": ["subject", "location"],
        "optional": {"small_noun": "figure"},
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "腰上中近景開場，結束在高空俯瞰",
        "shot_sizes": ["MCU", "MS", "CU"],
        "clause": ("the camera pulls out with large amplitude at fast speed while pedestalling up, rising and retreating "
                   "until {subject} is a small lone {small_noun} far below and the whole {location} opens out around "
                   "{subject}"),
        "note": "第 3 輪驗證：特寫→全身→高空俯拍，主角縮成小點；用 pull out 不是 zoom out。",
    },
    "super_dolly_in": {
        "aliases": ["super dolly in", "super dolly", "超長推軌", "長軌衝推", "超級推軌"],
        "slots": ["subject", "space", "near_objects", "further_objects", "ground"],
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "framing": "大遠景：沿 space 直看過去，near_objects 立在左右畫邊，主角小小在盡頭",
        "shot_sizes": ["ELS", "EWS", "XLS", "LS", "WS"],
        "clause": ("the camera pushes in with large amplitude at fast speed, charging the entire length of {space} toward "
                   "{subject}: {near_objects} sweep outward past the edges of frame and out of shot as the camera passes "
                   "them, {further_objects} rush by on both sides and {ground} streams underneath, and the move ends in "
                   "a tight close-up with {face} filling the frame"),
        "caution": "space／near_objects／further_objects／ground 必須是主角所在的同一地點，否則地理會怪（第 3 輪夜市接屋頂）。",
        "note": "第 3 輪驗證；一定要有左右兩個近景物件掃出畫面，否則退化成急推。",
    },
    "yoyo_zoom": {
        "aliases": ["yo-yo zoom", "yoyo zoom", "yo yo zoom", "溜溜球變焦", "來回變焦"],
        "slots": ["subject", "place"],
        "optional": {"small_noun": "figure"},
        "status": "pass",
        "strong": True,
        "no_bg_plate": True,
        "min_seconds": 8,
        "framing": "特寫開場（臉填滿畫面），結束回到同一特寫",
        "shot_sizes": ["CU", "ECU", "BCU"],
        "clause": ("the camera begins in a tight close-up on {face}, then zooms out, starting slowly and accelerating "
                   "harder and harder as it goes until the whole view smears into motion blur and {subject} has fallen "
                   "away into the far distance, a tiny {small_noun} {place}; the camera holds there for about a second, "
                   "then zooms back in with large amplitude at fast speed, snapping across the entire distance in a "
                   "single instant to land tight on {face} again exactly as it began"),
        "note": "第 3 輪驗證（8 秒）；停留長短由 H3 決定，要精準請後製剪；不要刪 hold 句。",
    },
    "split_screen_3": {
        "aliases": ["split screen", "three panel split screen", "3 panel split", "三格分割", "三格分割畫面",
                    "分割畫面"],
        "slots": ["subject", "action", "action_short", "panel_1_angle", "panel_2_angle", "panel_3_angle"],
        "status": "pass",
        "strong": True,
        "layout_only": True,
        "min_seconds": 8,
        "framing": "自訂：三個等寬直格",
        "shot_sizes": [],
        "clause": ("the frame is divided into three equal vertical panels side by side, separated by thin black gutters; "
                   "the left panel holds {subject}, {action}; every panel is locked off and completely static, nothing "
                   "pans, zooms or moves at any point; the three panels open one after another: the left panel plays "
                   "from the very first frame, showing {panel_1_angle}, while the centre and right panels are solid "
                   "black; the centre panel stays solid black and then comes on, showing the same moment from "
                   "{panel_2_angle}; the right panel stays solid black longer than the centre one and comes on last, "
                   "showing {panel_3_angle}; for the remainder of the shot all three panels play together in perfect "
                   "sync, the same continuous {action_short} at the same instant from three different angles"),
        "caution": "版面效果（layout-only）：只能控制亮格順序，不能控制秒數（H3 約 2.5 秒內全亮）。",
        "note": "第 3 輪驗證（8 秒）；三格要同一瞬間同一動作的三個角度，不寫絕對秒數。",
    },
    "push_in": {
        "aliases": ['push in', '推進', '緩推', '推鏡'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera pushes in slowly and steadily toward {subject} from the first frame, the shot size tightens by about one step and ends with {subject} centred; the camera does not pan, tilt or zoom'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "pull_back": {
        "aliases": ['pull back', 'pull out', '後拉', '拉遠', '後退'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera pulls back slowly and steadily from {subject} from the first frame, the shot size widens by about one step and more of the surroundings enters the frame; {subject} stays centred and the camera does not pan or tilt'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "pan": {
        "aliases": ['pan', '橫搖', '水平搖鏡'],
        "slots": ['target'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera stays at one spot and pans smoothly to the right at medium speed from the first frame until {target} sits in the centre of the frame; no push, no tilt, the height stays the same'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "truck": {
        "aliases": ['truck', '橫移', '側移'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera trucks left at medium speed on a straight line parallel to {subject}, keeping the same distance and height from the first frame to the last; the camera does not pan or tilt, and the background slides past behind {subject}'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "follow": {
        "aliases": ['follow', '跟拍', '跟隨'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera follows {subject} from behind at the same walking pace, keeping a constant distance and the same shot size from the first frame to the last; {subject} stays in the centre of the frame while the background moves past'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "crane_up": {
        "aliases": ['crane up', '升降上升', '升鏡', '搖臂上升'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera cranes straight up at slow speed while keeping {subject} in the lower centre of the frame; the lens stays level, no pan, and the view widens to show more of the space around {subject}'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "crane_down": {
        "aliases": ['crane down', '搖臂下降', '降鏡'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera cranes straight down at slow speed from a high position until it reaches eye level with {subject}, who ends centred in the frame; the lens stays level and does not pan'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "low_angle": {
        "aliases": ['low angle', '仰拍', '低角度'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('a low-angle shot held from the first frame to the last: the camera sits near the ground and looks up at {subject}, who towers against the sky; the camera stays fixed in height and angle, with no tilt'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "static_hold": {
        "aliases": ['static hold', 'static', '固定鏡頭', '定鏡'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera is locked off on a tripod from the first frame to the last, framing {subject} at the same size and position throughout; no pan, tilt, push or zoom, only the action inside the frame moves'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "orbit": {
        "aliases": ['orbit', '環繞', '繞拍'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera trucks left at medium speed while panning right to keep {subject} centred, travelling about 90 degrees around {subject} at a constant distance; the background rotates behind {subject}'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "rise_orbit": {
        "aliases": ['rise orbit', 'rising orbit', '上升環繞'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera trucks left while panning right to keep {subject} centred and pedestals up at the same time, circling about 90 degrees around {subject} as it climbs, ending in a high angle looking down at {subject}'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "steadicam": {
        "aliases": ['steadicam', '穩定器跟拍', '斯坦尼康'],
        "slots": ['subject'],
        "status": "untested",
        "strong": False,
        "clause": ('a smooth steadicam shot glides alongside {subject} at walking pace for the whole shot, keeping a constant distance and the same shot size; the motion is fluid with no shake, the camera does not pan away from {subject}'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "macro_push": {
        "aliases": ['macro push', '微距推進', '微距特寫推進'],
        "slots": ['detail'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera pushes in slowly toward {detail} from a close start until it fills the frame edge to edge, in extreme close-up with a very shallow depth of field; the background stays soft and blurred, no pan or tilt'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "rack_focus": {
        "aliases": ['rack focus', '轉焦', '焦點轉移'],
        "slots": ['foreground', 'background_subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the camera stays locked off; the shot begins with {foreground} in sharp focus and the background blurred, then the focus shifts smoothly until {background_subject} is sharp and {foreground} turns soft; no camera movement'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "aerial_reveal": {
        "aliases": ['aerial reveal', '空拍揭示', '高空揭示'],
        "slots": ['subject', 'location'],
        "status": "untested",
        "strong": False,
        "clause": ('an aerial shot that starts low behind a foreground obstacle and rises forward at medium speed, passing over it to reveal {location} stretching out below, with {subject} small in the middle of the view; the lens points slightly down'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "whip_pan": {
        "aliases": ['whip pan', '甩鏡', '快速搖鏡'],
        "slots": ['target'],
        "status": "untested",
        "strong": True,
        "clause": ('the camera whips to the right at very fast speed, the picture smearing into horizontal motion blur, and snaps to a stop with {target} sharp in the centre of the frame; the end frame is stable'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "crash_zoom": {
        "aliases": ['crash zoom', '急推變焦', '暴推'],
        "slots": ['subject'],
        "status": "untested",
        "strong": True,
        "clause": ('the camera zooms in at very fast speed in a single sudden move straight onto {subject}, ending in a tight close-up with {subject} centred and sharp; no pan, no tilt, the camera body does not move'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "fpv": {
        "aliases": ['fpv', 'fpv drone', '第一人稱穿越機', '穿越機'],
        "slots": ['space'],
        "status": "untested",
        "strong": True,
        "clause": ('a fast fpv drone shot that flies forward at high speed through {space}, banking and diving around obstacles at close range; the horizon rolls slightly and the background rushes past in streaks'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "pov": {
        "aliases": ['pov', '主觀鏡頭', '第一人稱視角'],
        "slots": ['viewer', 'target'],
        "status": "untested",
        "strong": False,
        "clause": ('a first-person point-of-view shot through the eyes of {viewer}: the camera moves forward at walking pace with slight natural sway toward {target}, which grows in the frame; {viewer} is never seen'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
    },
    "foreground_wipe": {
        "aliases": ['foreground wipe', '前景遮擋轉場', '遮擋轉場'],
        "slots": ['wipe_object', 'subject'],
        "status": "untested",
        "strong": False,
        "clause": ('the shot starts with {wipe_object} passing very close in front of the lens and filling the whole frame; as it slides out of frame the view clears to reveal {subject}; the camera itself stays still'),
        "note": 'PR-15b 未實測（參考 24frames.art 的判斷、用自己的話改寫）；首次生成請當測試看。',
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


BACKEND_SECONDS = (5, 8, 10, 15)  # Colab 後端只收這些秒數（家機 FreeVideo 無此限制）
SUBJECT_KINDS = ("person", "animal", "bird", "object")
_EYE_SIDES = {"right": "right", "left": "left", "右": "right", "左": "left"}


def _norm(s: str) -> str:
    return str(s or "").strip().lower().replace("-", "_").replace(" ", "_")


def find_preset(name: str) -> str:
    """名稱或別名 → preset id；找不到回傳空字串。"""
    key = _norm(name)
    for pid, spec in PRESETS.items():
        if key == pid or key in {_norm(a) for a in spec["aliases"]}:
            return pid
    return ""


def required_seconds(name: str, seconds: Optional[float] = None) -> int:
    """回傳此預設應使用的後端秒數（5/8/10/15）：不足 min_seconds 自動升到最小可用值。"""
    pid = find_preset(name)
    if not pid:
        raise ValueError(f"未知的 move_preset: {name!r}")
    need = max(float(seconds or 0), float(PRESETS[pid].get("min_seconds", 0)))
    for opt in BACKEND_SECONDS:
        if opt >= need - 1e-6:
            return opt
    return BACKEND_SECONDS[-1]


def expand_preset(name: str, slots: Optional[dict] = None, *, seconds: Optional[float] = None,
                  shot_size: Optional[str] = None, bg_plate: bool = False) -> Tuple[str, List[str]]:
    """回傳（Camera 子句, 警告）。未知預設、缺槽位或槽位值不合法 → ValueError。

    seconds：所在段落秒數，不足 min_seconds 時警告並給建議秒數。
    shot_size：該鏡景別代碼，與預設建議開場構圖不符時警告。
    bg_plate：是否掛了背景／場景參考圖，no_bg_plate 預設會警告運鏡幅度砍半。
    """
    pid = find_preset(name)
    if not pid:
        raise ValueError(f"未知的 move_preset: {name!r}；可用：{', '.join(sorted(PRESETS))}")
    slots = {k: str(v).strip() for k, v in (slots or {}).items() if str(v or "").strip()}
    # direction 槽位：dolly zoom 反向等改指向對應預設（LF：兩方向是兩個鏡頭）
    direction = slots.get("direction", "").lower()
    variants = PRESETS[pid].get("direction_variants") or {}
    if direction and direction not in ("forward", "正向", "wide"):
        if direction not in variants:
            raise ValueError(f"move_preset {pid} 不支援 direction={direction!r}；可用：forward、{'、'.join(variants)}")
        pid = variants[direction]
    spec = PRESETS[pid]
    missing = [k for k in spec["slots"] if k not in slots]
    if missing:
        raise ValueError(f"move_preset {pid} 缺必填槽位 {missing}（camera_optics.move_slots）")
    warnings: List[str] = []
    kind = slots.get("subject_kind", "person").lower()
    if kind not in SUBJECT_KINDS:
        raise ValueError(f"move_preset {pid} 的 subject_kind={kind!r} 不合法；可用：{', '.join(SUBJECT_KINDS)}")
    values = dict(spec.get("optional") or {})
    values.update(slots)
    subject = values.get("subject", "the subject")
    values.setdefault("face", subject if kind == "object" else f"{subject}'s face")
    if pid == "eyes_in" and "detail" not in values:
        if kind == "object":
            raise ValueError("move_preset eyes_in 用在物件主體時必須給 detail 槽位（例如某個刻印或鉚釘）")
        eye = _EYE_SIDES.get(values.get("eye", "right").lower())
        if not eye:
            raise ValueError(f"move_preset eyes_in 的 eye={values.get('eye')!r} 不合法；可用：right、left")
        values["detail"] = f"{subject}'s {eye} eye, the iris and pupil filling the view"
    if spec.get("moving_subject") and kind == "object":
        warnings.append(f"move_preset {pid} 需要主體自己移動（鏡頭綁在主體上）；靜止物件撐不起這個鏡頭")
    if kind != "person":
        warnings.append(f"move_preset {pid} 只驗證過人物主體；subject_kind={kind} 首次生成請當測試看")
    if spec["status"] != "pass":
        warnings.append(f"move_preset {pid} 為{spec['status']}：{spec['note']}")
    if spec.get("caution"):
        warnings.append(f"move_preset {pid}：{spec['caution']}")
    min_s = spec.get("min_seconds")
    if min_s and seconds is not None and float(seconds) < min_s - 1e-6:
        warnings.append(f"move_preset {pid} 需至少 {min_s} 秒（目前 {float(seconds):g} 秒），"
                        f"請把段落升到 {required_seconds(pid, seconds)} 秒，否則動作放不下")
    sizes = spec.get("shot_sizes") or []
    if shot_size and sizes and str(shot_size).strip().upper() not in sizes:
        warnings.append(f"move_preset {pid} 建議開場構圖：{spec['framing']}（目前景別 {shot_size}）")
    if bg_plate and spec.get("no_bg_plate"):
        warnings.append(f"move_preset {pid} 掛了背景參考圖：運鏡幅度約砍半，強運鏡請只掛角色參考圖")
    return spec["clause"].format(**values), warnings
