#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_ch02_layer2_and_h3.py
第二章（要是遇到第三次）階段 4 & 5 完整資料產出腳本
依據《噩盡島》實戰定案五大鐵律，為 EP01、EP02、EP03 建立：
1. ch02/layer2/ 下的 30 個 Layer 2 分鏡 JSON（每集 10 段，每段 8.0s，共 240s）
2. 自動推導掛載 MiniMax H3 LoRA
3. ch02/prompts-ep01~03.md（H3 官方六段式提示詞包）
4. ch02/segments-ep01~03.json（分段對帳檔）
"""

import os
import sys
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from director_storyboard_assistant import auto_adapt_h3_loras

BASE_CH02 = Path(r"C:\Users\kirit\OneDrive\文件\噩盡島\噩盡島-漫劇\ch02")
LAYER2_DIR = BASE_CH02 / "layer2"
LAYER2_DIR.mkdir(parents=True, exist_ok=True)

# 資產常數定義
STYLE_LOCK_ANCHOR = "3D animated series still, stylized realistic CG render, thick-paint texture over subsurface-scattering skin, cinematic volumetric lighting, shallow depth of field, detailed hair and fabric, 16:9"
LIGHTING_S01_02 = "Warm sunset golden-hour sunlight casting long angled amber shadows across the grey concrete walls, rim lighting on characters"
LIGHTING_S03_FASTFOOD = "Flickering pale cool fluorescent ceiling tube lights casting harsh downward shadows, alternating with dim amber reflections from the kitchen"
LIGHTING_S03_FASTFOOD_FIGHT = "Flickering pale cool fluorescent ceiling tube lights casting harsh downward shadows, bloody reflections on shiny ceramic tiles"
LIGHTING_S03_TIME_DILATION = "Time-dilation slow-motion ethereal amber luminescence suspended in air, flickering tube lights frozen mid-cycle"
LIGHTING_S03_POLICE_SHOOT = "Harsh direct flashlight beams from police pistols cutting through smoke and rain, broken glass reflecting street neon"
LIGHTING_S04_STATION_SLIME = "Vast modern transit concourse with high steel trusses, dim cool white ambient lights, eerie blue-white bioluminescence from sewer manhole"
LIGHTING_S04_STATION_AXE = "Dim flickering commercial ceiling lamps reflecting in slime jelly, harsh emergency red siren glow from hydrant cabinet"
LIGHTING_S04_STATION_DUO = "Brilliant cyan lightning blade aura cutting through dark shadows, cold metallic dagger highlights, cool ambient transit concourse"
LIGHTING_S04_STATION_GRAVITY = "Intense crushing gravitational purple-black aura ripples distorting air, brilliant cyan electric sparks erupting along broadsword edge"
LIGHTING_S04_STATION_RESOLVE = "Post-battle calm amber station commercial lights returning, smoke rising from blackened charred slime residue, clean sharp shadows"

# 參考圖常數定義
REF_SCENE_ALLEY = {"id": "S-school-alley", "type": "scene", "path": "images/scene-school-alley.png", "description": "narrow alley behind high school at dusk with textured grey concrete walls stained with moss in warm sunset golden-hour light"}
REF_SCENE_FASTFOOD = {"id": "S-fast-food-restaurant", "type": "scene", "path": "images/scene-fast-food.png", "description": "ordinary Taiwanese cafeteria interior with pale green formica tables and round steel stools under flickering fluorescent ceiling lights"}
REF_SCENE_STATION = {"id": "S-banqiao-station-hall", "type": "scene", "path": "images/scene-banqiao-station.png", "description": "vast transit station concourse with high steel-truss ceiling and polished grey granite tiled floor reflecting dim commercial lights"}

REF_CHAR_SHEN = {"id": "C-shen-luonian", "type": "character", "is_primary_character": True, "path": "images/char-ShenLuonian.png", "description": "Shen Luonian, a 16-year-old Taiwanese boy, pale fair skin, neat short black hair with a few loose strands falling over the forehead, dark brown eyes, slim slightly frail-looking build, wearing a white short-sleeved private-high-school uniform shirt with navy collar trim, a calm indifferent expression, a raised reddish scar along the outer left forearm"}
REF_CHAR_LAI = {"id": "C-lai-yixin", "type": "character", "is_primary_character": True, "path": "images/char-LaiYixin.png", "description": "Lai Yixin, an athletic 17-year-old Taiwanese boy, tall sturdy build, round boyish handsome face, short spiky black hair, bright enthusiastic dark eyes, wearing a white high-school uniform shirt with rolled sleeves, carrying a white leather long backpack on his back, a sunny confident smile"}
REF_CHAR_YE = {"id": "C-ye-weishan", "type": "character", "is_primary_character": True, "path": "images/char-YeWeishan.png", "description": "Ye Weishan, a graceful 17-year-old Taiwanese high-school girl, fair delicate skin, long straight black hair falling past her shoulders, elegant refined facial features, intelligent clear eyes, wearing a white high-school uniform shirt and a pleated navy knee-length skirt, carrying a white silk handkerchief, a composed serious and slightly aloof expression"}
REF_CHAR_HUANG = {"id": "C-huang-zongru", "type": "character", "is_primary_character": False, "path": "images/char-HuangZongru.png", "description": "Huang Zongru, a short chubby Taiwanese boy of 17, round face, thick black-framed glasses, oily short black hair, oversized white school uniform shirt, hunched timid posture, nervous trembling expression"}
REF_CHAR_SLAYER = {"id": "C-brown-hair-slayer", "type": "character", "is_primary_character": True, "path": "images/char-BrownHairSlayer.png", "description": "A spirited Taiwanese woman in her early twenties, athletic toned build, unruly caramel-brown hair cut just past the ears, wide bright eyes, a wide fearless grin, wearing an oversized beige crewneck short-sleeve shirt, knee-length black compression shorts, high-top sneakers, wielding a heavy carved cyan steel broadsword"}
REF_CHAR_DAOIST = {"id": "C-black-hair-daoist", "type": "character", "is_primary_character": True, "path": "images/char-BlackHairDaoist.png", "description": "A calm Taiwanese woman in her early twenties, slender agile build, slicked-back stylish very short black hair, small delicate face with long eyelashes, fine pale skin, wearing a loose dark-grey windbreaker over tight black jeans and ankle boots, holding a narrow matte-silver dagger, a cool observant and composed expression"}
REF_CREATURE_RAT = {"id": "CREATURE-giant-rat", "type": "character", "is_primary_character": False, "path": "images/creature-giant-rat.png", "description": "A monstrous grey-black rat, over one metre in length, coarse dark fur, pinkish-grey muscular flesh pillar tail, glowing crimson bead-like eyes, razor-sharp curved incisors, agile predatory stance"}
REF_CREATURE_SLIME = {"id": "CREATURE-jelly-slime", "type": "character", "is_primary_character": False, "path": "images/creature-jelly-slime.png", "description": "A colossal translucent blue-white gelatinous slime monster, two metres tall and five metres wide, quivering flesh, semi-transparent body revealing swallowed objects, undulating skirt-like membranes"}

def make_shot_data(
    shot_id: str,
    start_time: float,
    duration: float,
    dramatic_beat_type: str,
    shot_size: str,
    focal_length: str,
    physical_distance: str,
    pov_routing: str,
    movement: str,
    axis_side: str,
    anchor_objects: list,
    blocking_desc: str,
    action_stages: list,
    observable_expression: str,
    has_dialogue: bool,
    speaker: str = None,
    line_verbatim: str = None,
    voice_4d_spec: str = None,
    foley: str = "環境底噪",
    h3_action_en: str = "",
    h3_camera_en: str = "static"
) -> dict:
    end_time = round(start_time + duration, 2)
    shot_obj = {
        "shot_id": shot_id,
        "start_time": start_time,
        "end_time": end_time,
        "duration": duration,
        "dramatic_beat_type": dramatic_beat_type,
        "camera_optics": {
            "shot_size": shot_size,
            "focal_length": focal_length,
            "physical_distance": physical_distance,
            "pov_routing": pov_routing,
            "movement": movement,
            "axis_side": axis_side
        },
        "spatial_blocking": {
            "anchor_objects": anchor_objects,
            "blocking_desc": blocking_desc,
            "safe_zone_9x16_passed": True
        },
        "action_and_performance": {
            "action_stages": action_stages,
            "observable_expression": observable_expression,
            "background_idle_life": "微風掠過衣擺，光影保持自然抖動",
            "micro_physics_tail": "衣角與髮絲隨動作慣性自然下垂"
        },
        "dialogue_and_audio": {
            "has_dialogue": has_dialogue,
            "speaker": speaker,
            "line_verbatim": line_verbatim,
            "voice_4d_spec": voice_4d_spec,
            "delivery_timing_anchor": "start_immediate" if has_dialogue else None,
            "lips_closed_lock": not has_dialogue,
            "audio_bridge": "NONE",
            "foley_and_ambience": foley
        },
        "_h3_action_en": h3_action_en,
        "_h3_camera_en": h3_camera_en
    }
    # 自動掛載 LoRA
    lora_res = auto_adapt_h3_loras(shot_obj, enable_camera_lora=False)
    shot_obj["h3_loras"] = lora_res.get("loras", [])
    return shot_obj


def make_segment_data(
    project_id: str,
    scene_id: str,
    segment_id: str,
    source_scene_id: str,
    lighting_lock: str,
    ref_images: list,
    shots: list,
    end_state_desc: str,
    h3_summary_en: str,
    h3_soundscape_en: str,
    h3_music_en: str
) -> dict:
    target_duration_sec = round(sum(s["duration"] for s in shots), 2)
    # 建立 H3 提示詞
    sub_def_lines = []
    retention_lines = []
    
    # Picture 1: 場景
    scene_ref = ref_images[0]
    sub_def_lines.append(f"<Picture 1> is the establishing plate of {scene_ref['description']}.")
    retention_lines.append(f"<Picture 1> (first frame): fully_preserved - the background environment layout and architectural lighting are retained.")
    
    # Picture 2..N: 角色
    for idx, ref in enumerate(ref_images[1:], start=1):
        pic_num = idx + 1
        sub_def_lines.append(f"<Subject {idx}> is the character in <Picture {pic_num}>, {ref['description']}.")
        retention_lines.append(f"<Subject {idx}> (appears across shots): fully_preserved - the facial likeness, hairstyle, and wardrobe details from <Picture {pic_num}> are retained.")

    sub_defs_text = "\n".join(sub_def_lines)
    retention_text = "\n".join(retention_lines)

    # Detailed description
    desc_lines = [f"The target video is stylized 3D anime CG animation, illuminated by natural {lighting_lock}."]
    for idx, s in enumerate(shots, start=1):
        cam = s["_h3_camera_en"]
        act = s["_h3_action_en"]
        dlg_part = ""
        if s["dialogue_and_audio"]["has_dialogue"]:
            spk = s["dialogue_and_audio"]["speaker"]
            line = s["dialogue_and_audio"]["line_verbatim"]
            dlg_part = f" Then the character says with clear lip sync: <d>[Audio]{line}</d>."
        
        if idx == 1:
            desc_lines.append(f"[Shot 1] The shot begins from <Picture 1>: eye-level medium shot as the camera {cam}, then {act}.{dlg_part}")
        else:
            ts_str = f"At 00:{s['start_time']:04.2f}"
            desc_lines.append(f"[Shot {idx}] {ts_str}, the shot cuts to a medium close-up as the camera {cam}, then {act}.{dlg_part}")

    detailed_desc_text = "\n".join(desc_lines)

    h3_prompt_text = f"""subject_definitions:
{sub_defs_text}

summary:
[keyframe completion + reference generation] {h3_summary_en}

retention_analysis:
{retention_text}

detailed_description:
{detailed_desc_text}

overall_soundscape:
{h3_soundscape_en}

non_diegetic_music:
{h3_music_en}"""

    # 乾淨移除暫存 key
    clean_shots = []
    for s in shots:
        s_copy = dict(s)
        s_copy.pop("_h3_action_en", None)
        s_copy.pop("_h3_camera_en", None)
        clean_shots.append(s_copy)

    seg_obj = {
        "project_id": project_id,
        "scene_id": scene_id,
        "segment_id": segment_id,
        "source_scene_id": source_scene_id,
        "metadata": {
            "aspect_ratio": "16:9",
            "target_duration_sec": target_duration_sec,
            "pacing_profile": "Fast_ShortDrama",
            "lighting_lock_line": lighting_lock
        },
        "continuity_handshake": {
            "mode": "INDEPENDENT_REF2VA",
            "inherited_from_segment": None,
            "overflow_dialogue_in": None,
            "overflow_dialogue_out": None,
            "persistent_world_state": [end_state_desc]
        },
        "shots": clean_shots,
        "segment_end_state": {
            "planned_final_state": {
                "description": end_state_desc
            },
            "observed_final_state": None
        },
        "reference_images": ref_images,
        "h3_prompt": h3_prompt_text
    }
    return seg_obj

helpers = {
    "make_shot": make_shot_data,
    "make_segment": make_segment_data,
    "constants": {
        "LIGHTING_S01_02": LIGHTING_S01_02,
        "LIGHTING_S03_FASTFOOD": LIGHTING_S03_FASTFOOD,
        "LIGHTING_S03_FASTFOOD_FIGHT": LIGHTING_S03_FASTFOOD_FIGHT,
        "LIGHTING_S03_TIME_DILATION": LIGHTING_S03_TIME_DILATION,
        "LIGHTING_S03_POLICE_SHOOT": LIGHTING_S03_POLICE_SHOOT,
        "LIGHTING_S04_STATION_SLIME": LIGHTING_S04_STATION_SLIME,
        "LIGHTING_S04_STATION_AXE": LIGHTING_S04_STATION_AXE,
        "LIGHTING_S04_STATION_DUO": LIGHTING_S04_STATION_DUO,
        "LIGHTING_S04_STATION_GRAVITY": LIGHTING_S04_STATION_GRAVITY,
        "LIGHTING_S04_STATION_RESOLVE": LIGHTING_S04_STATION_RESOLVE,
        "REF_SCENE_ALLEY": REF_SCENE_ALLEY,
        "REF_SCENE_FASTFOOD": REF_SCENE_FASTFOOD,
        "REF_SCENE_STATION": REF_SCENE_STATION,
        "REF_CHAR_SHEN": REF_CHAR_SHEN,
        "REF_CHAR_LAI": REF_CHAR_LAI,
        "REF_CHAR_YE": REF_CHAR_YE,
        "REF_CHAR_HUANG": REF_CHAR_HUANG,
        "REF_CHAR_SLAYER": REF_CHAR_SLAYER,
        "REF_CHAR_DAOIST": REF_CHAR_DAOIST,
        "REF_CREATURE_RAT": REF_CREATURE_RAT,
        "REF_CREATURE_SLIME": REF_CREATURE_SLIME
    }
}

from ch02_data_ep01 import get_ep01_segments
from ch02_data_ep02 import get_ep02_segments
from ch02_data_ep03 import get_ep03_segments

episodes = {
    "01": get_ep01_segments(helpers),
    "02": get_ep02_segments(helpers),
    "03": get_ep03_segments(helpers)
}

print(f"Loaded segments: EP01={len(episodes['01'])}, EP02={len(episodes['02'])}, EP03={len(episodes['03'])}")

for ep_num, segs in episodes.items():
    print(f"\nWriting files for EP{ep_num}...")
    # 1. 寫入 Layer 2 JSON
    for seg in segs:
        seg_id = seg["segment_id"]
        out_path = LAYER2_DIR / f"layer2-{seg_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(seg, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"  - Written: {out_path.name}")

    # 2. 寫入 segments-epNN.json 對帳檔
    seg_list_path = BASE_CH02 / f"segments-ep{ep_num}.json"
    with open(seg_list_path, "w", encoding="utf-8") as f:
        json.dump(segs, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"  - Written segments list: {seg_list_path.name}")

    # 3. 寫入 prompts-epNN.md
    prompts_md_path = BASE_CH02 / f"prompts-ep{ep_num}.md"
    md_lines = [
        f"# 第二章 EP{ep_num} H3 官方六段式提示詞包",
        "",
        "> 依據 MiniMax H3 官方規範與 FreeVideo 17n+5 規格自動編譯",
        f"> 全集共 {len(segs)} 個分段，總時長 {sum(s['metadata']['target_duration_sec'] for s in segs):.1f} 秒",
        ""
    ]
    for seg in segs:
        seg_id = seg["segment_id"]
        dur = seg["metadata"]["target_duration_sec"]
        md_lines.extend([
            f"## {seg_id}",
            f"- 時長：{dur:.1f}s",
            f"- 鏡頭數：{len(seg['shots'])}",
            f"- 連戲狀態：{seg['continuity_handshake']['persistent_world_state'][0]}",
            "",
            "```text",
            seg["h3_prompt"],
            "```",
            ""
        ])
    with open(prompts_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"  - Written prompts package: {prompts_md_path.name}")

print("\nAll Layer 2 and H3 assets successfully written!")

