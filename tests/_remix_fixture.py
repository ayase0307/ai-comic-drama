"""PR-R5 測試共用的 REMIX 專案 fixture（EP04-S02-d 類：場景＋三個演員＝4 包、三人對話段）。

角色與場景取自《噩盡島》ch02 EP04 的後巷段落（ch02/build.py 的實戰送件格式），文字為測試改寫；
不需要任何圖檔：remix 綁定的是家機角色包，編譯器不讀本機參考圖。
"""
import json
from pathlib import Path

import decisions  # noqa: F401  （呼叫端已把 scripts 放進 sys.path）

ANCHOR = ("Stylized East Asian 3D CG, Unreal Engine 5 next-gen CG cinema aesthetic, realistic East Asian bone "
          "structure, subsurface-scattering skin, clearly a 3D CG render (not a photograph).")

BIBLE = {
    "characters": [
        {"character_id": "C-YE", "canonical_name": "葉衛珊", "name_en": "Ye Weishan",
         "visual_prompt_en": ("a slender 18 year old girl with a delicate oval face, glossy straight black hair "
                              "to the middle of her back, in a white short-sleeve school blouse and a navy pleated skirt")},
        {"character_id": "C-LAI", "canonical_name": "賴一心", "name_en": "Lai Yixin",
         "visual_prompt_en": ("a tall athletic 18 year old boy with short black sporty hair, thick brows and a healthy tan, "
                              "in a white short-sleeve school shirt and navy trousers")},
        {"character_id": "C-SHEN", "canonical_name": "沈洛年", "name_en": "Shen Luonian",
         "visual_prompt_en": ("a slim pale 17 year old boy with a messy dusty black fringe and calm narrow monolid eyes, "
                              "in a dusty white school shirt with a torn right cuff and navy trousers")},
    ],
    "locations": [
        {"location_id": "S-ALLEY", "name": "後巷", "name_en": "back alley",
         "visual_prompt_en": ("a narrow concrete service alley behind a Taiwanese high-school classroom block, plain grey "
                              "water-stained walls with one cracked section, rusty drainpipes and a raised flower bed")},
    ],
}

PACKS = {"packs": {
    "S-ALLEY": {"default": "ejin3_scene_backalley", "tag": "Picture", "kind": "scene"},
    "C-YE": {"default": "ejin3_yeweishan", "tag": "Video", "kind": "actor"},
    "C-LAI": {"default": "ejin3_laiyixin", "tag": "Video", "kind": "actor"},
    "C-SHEN": {"default": "ejin3_shenluonian", "tag": "Video", "kind": "actor"},
}}

FIVE_1 = {
    "camera": ("Eye-level medium-wide framing from the alley entrance at chest height, the cracked wall along frame left "
               "and the flower bed along frame right."),
    "motion": ("From left to right: {C-SHEN}, {C-LAI}, {C-YE}. First {C-YE} walks along the flower bed toward {C-LAI}, "
               "then {C-LAI} turns his head back over his right shoulder toward her and squares his whole body to her, "
               "while {C-SHEN} presses his right palm on the cracked wall and starts pushing himself up."),
    "performance": ("{C-YE} keeps her eyes on {C-LAI} toward frame left with a small cool frown and pressed lips; "
                    "{C-LAI} breaks into a broad grin, brows lifted."),
    "light": ("Warm late-afternoon sunlight slants across the walls from frame right and lights every face evenly, "
              "with soft dust hanging in the beams."),
    "sound": "Light footsteps on concrete, the scrape of a shoe on grit and a distant school bell echo.",
}
FIVE_2 = {
    "camera": ("Medium two-shot at a slightly lower angle, still from the entrance side, the pair framed center-right "
               "with the wall soft on frame left."),
    "motion": ("{C-YE} stops at the right side of {C-LAI}; first she flicks her eyes down at the dusty ground, then back "
               "up to him, as {C-LAI} nods and points his free left hand down at the ground between them."),
    "performance": ("{C-YE} tilts her chin up with a faint sniff of distaste; {C-LAI} answers with an eager nod and "
                    "bright, wide-open eyes."),
    "light": ("The same warm sunlight from frame right rims both faces, the wall behind them falling into soft cool shadow."),
    "sound": "A soft breeze through the alley, a drainpipe drip and fabric rustle as he points down.",
}


def layer2_doc():
    return {
        "segment_id": "EP04-S02-d", "scene_id": "S-ALLEY",
        "asset_refs": {"scene_id": "S-ALLEY", "characters": [{"id": "C-YE"}, {"id": "C-LAI"}, {"id": "C-SHEN"}]},
        "metadata": {"target_duration_sec": 7.0, "aspect_ratio": "16:9",
                     "lighting_lock_line": "warm late-afternoon sunlight from frame right",
                     "soundscape_en": "Quiet outdoor alley ambience with a distant school bell echo and light footsteps."},
        "positions": [{"id": "C-SHEN", "order_lr": 1, "axis_side": "left", "facing": "right"},
                      {"id": "C-LAI", "order_lr": 2, "axis_side": "left", "facing": "right"},
                      {"id": "C-YE", "order_lr": 3, "axis_side": "right", "facing": "left"}],
        "shots": [
            {"shot_id": "SH01", "start_time": 0.0, "end_time": 4.3, "duration": 4.3,
             "character_ids": ["C-SHEN", "C-LAI", "C-YE"],
             "camera_optics": {"shot_size": "MLS", "focal_length": "35mm", "physical_distance": "4m",
                               "movement_en": "dolly in"},
             "action_and_performance": {"action_stages_en": ["Ye Weishan walks toward Lai Yixin"],
                                        "five_part_en": FIVE_1},
             "dialogue_and_audio": {"has_dialogue": True, "speaker": "C-YE",
                                    "line_verbatim": "他們又用不到，當然是我們的。",
                                    "voice_4d_spec_en": "a composed teenage girl with a cool, crisp, clear voice"}},
            {"shot_id": "SH02", "start_time": 4.3, "end_time": 7.0, "duration": 2.7,
             "character_ids": ["C-LAI", "C-YE"],
             "camera_optics": {"shot_size": "MS", "focal_length": "50mm", "physical_distance": "2.5m",
                               "movement": "static"},
             "action_and_performance": {"action_stages_en": ["Ye Weishan stops beside Lai Yixin"],
                                        "five_part_en": FIVE_2},
             "dialogue_and_audio": {"has_dialogue": False}},
        ],
    }


def write_project(root: Path, *, decide_backend=True, anchor=True, packs=None, layer2=None) -> Path:
    """在 root 建好 remix 專案（layer2、bible、包計畫表、decisions）；回傳 layer2 檔路徑。"""
    for name in ("layer2", "adapt", "assets"):
        (root / name).mkdir(parents=True, exist_ok=True)
    path = root / "layer2" / "layer2-EP04-S02-d.json"
    path.write_text(json.dumps(layer2 or layer2_doc(), ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "adapt" / "bible.json").write_text(json.dumps(BIBLE, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "assets" / "character-packs.json").write_text(
        json.dumps(packs or PACKS, ensure_ascii=False, indent=2), encoding="utf-8")
    if decide_backend:
        decisions.decide(root, "video_backend", "remix", "這章改用家機角色卡")
    if anchor:
        decisions.decide(root, "style_anchor", ANCHOR, "我們是 3D 厚塗")
    return path
