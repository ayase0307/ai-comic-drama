#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_all_tests.py — 建立 10 大邊界測試 Fixtures 與 A/B 對照樣本，並執行全套確定性驗證腳本
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

TESTS_DIR = Path(__file__).resolve().parent
SKILL_ROOT = TESTS_DIR.parent
SCRIPTS_DIR = SKILL_ROOT  # vendored: scripts/adapt/*.py sit beside tests/
FIXTURES_DIR = TESTS_DIR / "fixtures"
EXPECTED_DIR = TESTS_DIR / "expected"

sys.path.insert(0, str(SCRIPTS_DIR))

from check_continuity import audit_continuity
from compare_adaptation import evaluate_adaptation
from estimate_duration import estimate_script_duration
from validate_structure import parse_and_validate_script, validate_json_against_schema


def make_base_bible() -> Dict[str, Any]:
    return {
        "project_id": "test-manju-suite",
        "irreversible_states": ["destroyed", "burned", "dead"],
        "characters": [
            {
                "character_id": "lin-che",
                "canonical_name": "林澈",
                "aliases": ["阿澈", "七師兄", "林小友"],
                "role": "star",
            },
            {
                "character_id": "shen-ning",
                "canonical_name": "沈寧",
                "aliases": ["沈姑娘", "阿寧"],
                "role": "planet",
            },
            {
                "character_id": "zhao-kun",
                "canonical_name": "趙坤",
                "aliases": ["趙管事", "坤爺"],
                "role": "planet",
            },
            {
                "character_id": "wife",
                "canonical_name": "妻子",
                "aliases": ["林妻"],
                "role": "star",
            },
            {
                "character_id": "husband",
                "canonical_name": "丈夫",
                "aliases": ["老陳"],
                "role": "planet",
            },
        ],
    }


def make_valid_handoff(
    project_id: str,
    genre_mode: str,
    aspect_ratio: str,
    scenes: List[Dict[str, Any]],
    source_issues: List[Dict[str, Any]] = None,
    debt_ledger: List[Dict[str, Any]] = None,
    episodes_override: List[Dict[str, Any]] = None,
    target_sec: int = 20,
) -> Dict[str, Any]:
    if episodes_override is not None:
        eps = episodes_override
    else:
        eps = [
            {
                "episode_id": "EP01",
                "title": "測試集",
                "target_duration_seconds": target_sec,
                "episode_goal": "推進核心衝突並驗證連戲",
                "act_out_type": "revelation_twist",
                "scenes": scenes,
            }
        ]
    return {
        "project_id": project_id,
        "rights_status": "owned_original",
        "adaptation_mode": "balanced",
        "genre_mode": genre_mode,
        "aspect_ratio": aspect_ratio,
        "target_medium": "ai_animation",
        "source_gaps_or_contradictions": source_issues or [],
        "debt_ledger": debt_ledger
        or [
            {
                "debt_id": "debt-01",
                "origin_ep": "EP01",
                "payoff_ep": "EP02",
                "debtor": "lin-che",
                "description": "林澈隱瞞信件背面字跡，引來沈寧懷疑",
                "status": "open",
            }
        ],
        "episodes": eps,
    }


def build_test_cases() -> List[Dict[str, Any]]:
    """建構 10 個完整測試案例（含新 Skill 版本與負向/舊版對照組）。"""
    cases = []

    # Case 01: 高資訊密度但事件少的小說片段
    c1_source = {
        "case_id": "case01_high_density_low_event",
        "title": "高資訊密度但事件少的小說片段（壓縮設定不亂加劇情）",
        "novel_excerpt": (
            "【自編測試文本】舊曆年間，北城連下七日暴雨，郵政局停擺。林澈獨自住在破敗的舊公寓裡，"
            "他心裡清楚這封從南岸寄來的信意味著三年前那場礦難的撫恤金帳目已經曝光，內心焦慮萬分，"
            "反覆思考著該把信燒掉還是交給巡捕房。就在這時，門外傳來沈寧的敲門聲。"
        ),
        "genre_mode": "mystery_thriller",
        "story_units": [
            {"unit_id": "ch01:u1", "summary": "暴雨夜林澈面對浸濕的帳目信件陷入抉擇", "expected_grade": "COMPRESS"},
            {"unit_id": "ch01:u2", "summary": "沈寧敲門指出林澈已看過信", "expected_grade": "MUST_KEEP"},
        ],
    }
    c1_script = (
        "第01集｜回信\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧\n"
        "△窗外暴雨拍打玻璃。桌上放著一盞鐵皮火盆，旁邊是一封被水浸濕、印著『南岸礦務』紅章的信。\n"
        "△林澈右手捏著信紙湊近火盆火苗，門外突然傳來三下急促的敲門聲。他迅速縮手把信翻至背面。\n"
        "沈寧（門外，壓低聲音）：開門。我知道你看過那封信。\n"
        "△林澈手指僵住，信紙背面受熱浮現一行暗紅色字跡。\n"
        "林澈：這字……不是我寫的。\n"
    )
    c1_scene = {
        "project_id": "case01-project",
        "episode_id": "EP01",
        "scene_id": "EP01-S01",
        "source_refs": ["ch01:u1", "ch01:u2"],
        "adaptation_mode": "balanced",
        "setting": {"location": "old_apartment", "time": "night", "interior": True, "timeline_tag": "present"},
        "characters": ["lin-che", "shen-ning"],
        "scene_goal": "將暴雨背景與燒信抉擇外化為火盆與紅章信封動作",
        "dramatic_turn": "信紙受熱浮現陌生字跡且沈寧已在門外",
        "dialogue": [
            {"speaker": "shen-ning", "text": "開門。我知道你看過那封信。", "audio_type": "offscreen"},
            {"speaker": "lin-che", "text": "這字……不是我寫的。", "audio_type": "onscreen"},
        ],
        "props": ["wet_letter", "brazier"],
        "continuity_initial": {"wet_letter": "on_table"},
        "continuity_final": {"wet_letter": "in_lin_che_hand"},
        "estimated_duration_seconds": {"min": 14, "max": 23},
        "adaptation_changes": [
            {"type": "compress", "description": "將暴雨停擺與礦難心理獨白壓縮為『南岸礦務』紅章與火盆燒信動作", "source_ref": "ch01:u1"}
        ],
        "storyboard_handoff": {
            "recommended_generation_modes": ["I2V"],
            "required_visual_beats": ["南岸礦務紅章信封與火盆", "敲門聲驚動翻信", "信背浮現紅字"],
            "required_audio_beats": ["窗外暴雨聲", "三下敲門聲", "門外壓低聲音"],
            "must_preserve": ["信背受熱浮現字跡"],
        },
    }
    cases.append({
        "case_id": "case01_high_density_low_event",
        "source": c1_source,
        "script": c1_script,
        "handoff": make_valid_handoff("case01-project", "mystery_thriller", "9:16", [c1_scene]),
    })

    # Case 02: 重要事件與大量支線交錯
    c2_source = {
        "case_id": "case02_main_plot_vs_subplots",
        "title": "重要事件與大量支線交錯（保留主因果，合併支線）",
        "genre_mode": "mystery_thriller",
        "story_units": [
            {"unit_id": "ch02:u1_main", "summary": "趙坤逼林澈交出礦場帳冊", "expected_grade": "MUST_KEEP"},
            {"unit_id": "ch02:u2_sub_tea", "summary": "路人茶博士閒聊南城米價上漲三成", "expected_grade": "REMOVE"},
            {"unit_id": "ch02:u3_sub_henchman", "summary": "小嘍囉甲與小嘍囉乙分別威脅林澈", "expected_grade": "MERGE"},
        ],
    }
    c2_script = (
        "第01集｜逼帳\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、趙坤\n"
        "△趙坤一腳踩在門檻上，將一把帶泥的算盤重重拍在木桌上，算珠四散崩落。\n"
        "趙坤（冷笑）：天亮前見不到南岸帳冊，這間屋子就改姓趙。\n"
        "△林澈彎腰撿起一顆算珠，指尖擦過桌底暗格的鐵扣。\n"
        "林澈：帳冊不在我這，但當年簽字的人，現在就在門外吧？\n"
    )
    c2_scene = dict(c1_scene, project_id="case02-project", source_refs=["ch02:u1_main"], characters=["lin-che", "zhao-kun"])
    c2_scene["adaptation_changes"] = [
        {"type": "must_keep", "description": "保留趙坤逼交帳冊主衝突", "source_ref": "ch02:u1_main"},
        {"type": "remove", "description": "刪除無關主線的茶博士聊米價支線", "source_ref": "ch02:u2_sub_tea"},
        {"type": "merge", "description": "將兩名小嘍囉的威脅直接合併至核心反派趙坤一人身上", "source_ref": "ch02:u3_sub_henchman"},
    ]
    cases.append({
        "case_id": "case02_main_plot_vs_subplots",
        "source": c2_source,
        "script": c2_script,
        "handoff": make_valid_handoff("case02-project", "mystery_thriller", "9:16", [c2_scene]),
    })

    # Case 03: 跨章伏筆後續揭露（測試不提前洩底）
    c3_source = {
        "case_id": "case03_cross_chapter_foreshadow",
        "title": "跨章伏筆後續揭露（禁止提前洩底）",
        "genre_mode": "mystery_thriller",
        "story_units": [
            {"unit_id": "ch01:plant", "summary": "沈寧手腕有一道舊燙傷疤痕（第5章才揭曉她是礦長孤女）", "expected_grade": "MUST_KEEP"}
        ],
        "foreshadowing": [
            {
                "clue_id": "clue-scar",
                "min_reveal_scene_index": 2,
                "forbidden_early_spoiler_phrases": ["礦長孤女", "親生女兒"],
            }
        ],
    }
    c3_script = (
        "第01集｜疤痕\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧\n"
        "△沈寧伸手奪過桌上的信封，袖口滑落，露出一道月牙形的舊燙傷疤痕。\n"
        "△林澈的視線在那道疤痕上停留了一瞬，隨即移開。\n"
        "沈寧：看什麼？只是一道舊傷。\n"
        "林澈：沒什麼，只是見過類似的烙印。\n"
    )
    c3_scene = dict(c1_scene, project_id="case03-project", source_refs=["ch01:plant"])
    c3_scene["dialogue"] = [
        {"speaker": "shen-ning", "text": "看什麼？只是一道舊傷。", "audio_type": "onscreen"},
        {"speaker": "lin-che", "text": "沒什麼，只是見過類似的烙印。", "audio_type": "onscreen"},
    ]
    c3_scene["storyboard_handoff"] = {
        "recommended_generation_modes": ["I2V"],
        "required_visual_beats": ["袖口滑落露出月牙形燙傷", "林澈眼神停頓"],
        "required_audio_beats": ["衣料摩擦聲"],
        "must_preserve": ["月牙形燙傷特寫（僅展示視覺線索，嚴禁提前點破礦長孤女身份）"],
    }
    cases.append({
        "case_id": "case03_cross_chapter_foreshadow",
        "source": c3_source,
        "script": c3_script,
        "handoff": make_valid_handoff("case03-project", "mystery_thriller", "9:16", [c3_scene]),
    })

    # Case 04: 多角色同名或別名（角色追蹤不混亂）
    c4_source = {
        "case_id": "case04_character_aliases",
        "title": "多角色同名或別名消歧（對白可用稱謂，發言人欄強制標準名）",
        "genre_mode": "mystery_thriller",
        "story_units": [
            {"unit_id": "ch04:u1", "summary": "沈寧稱呼林澈為七師兄，趙坤稱呼林澈為林小友", "expected_grade": "MUST_KEEP"}
        ],
    }
    c4_script = (
        "第01集｜舊識\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧、趙坤\n"
        "△沈寧擋在木桌前，趙坤站在門口拍去肩頭雨水。\n"
        "沈寧：七師兄，別聽他胡說！\n"
        "趙坤（皮笑肉不笑）：林小友，連阿寧都勸你了，何必執迷不悟？\n"
        "林澈：趙管事請回吧。\n"
    )
    c4_scene = dict(
        c1_scene,
        project_id="case04-project",
        source_refs=["ch04:u1"],
        characters=["lin-che", "shen-ning", "zhao-kun"],
    )
    cases.append({
        "case_id": "case04_character_aliases",
        "source": c4_source,
        "script": c4_script,
        "handoff": make_valid_handoff("case04-project", "mystery_thriller", "9:16", [c4_scene]),
    })

    # Case 05: 無戰鬥的情緒戲（拒絕強迫逆襲打臉，並同時作為與「原始滿血版提示詞」的 A/B 基準測試！）
    c5_source = {
        "case_id": "case05_emotional_no_combat",
        "title": "無戰鬥的溫情傷感戲（孕婦丟失500元——對照原始滿血版提示詞示例）",
        "novel_excerpt": (
            "懷孕七個月那天，妻子從菜市場買菜回來，和丈夫通電話時不小心把兜裡的五百塊錢掉在了濕漉漉的水泥地上。"
            "回到臥室後，她翻遍了棕色皮包、黑色包包和卡其色外套口袋都找不到那五百塊錢，心裡十分自責，"
            "摸著肚子覺得自己很沒用。"
        ),
        "genre_mode": "healing_literary",
        "story_units": [
            {"unit_id": "ch05:u1_market", "summary": "菜市場妻子邊走邊接丈夫關心電話，五百元從口袋滑落地面未察覺", "expected_grade": "MUST_KEEP"},
            {"unit_id": "ch05:u2_bedroom", "summary": "回到臥室翻找外套與皮包無果，撫摸孕肚自責落淚", "expected_grade": "MUST_KEEP"},
        ],
    }
    # 新 Skill 改編版：修正時間線標記（加上（閃回）或按正敘排列，消除首句冗餘說明畫外音，絕不強加打臉）
    c5_script = (
        "第01集｜五百塊\n\n"
        "1-1 臥室 日/內\n"
        "人物：妻子\n"
        "△懷孕七個月的妻子穿著米色針織開衫坐在床邊，焦急地將棕色皮包裡的零碎收據全部倒在床單上。\n"
        "△她抓起卡其色外套用力抖了抖，空蕩蕩的口袋翻了出來。\n"
        "妻子（聲音發顫）：不可能啊……我明明裝兜里了。\n"
        "1-2 菜市場 日/外（閃回）\n"
        "人物：妻子、丈夫\n"
        "△清晨人來人往的菜市場，妻子左手拎著青菜與鮮魚，右手舉著手機貼在耳邊，臉上帶著溫柔笑意。\n"
        "丈夫（電話音）：慢點走，別買太重的。\n"
        "△妻子把菜袋換到右手，幾張百元鈔票從外套側袋邊緣滑落，飄在濕漉漉的水泥地上。她毫未察覺地向前走遠。\n"
        "妻子：知道了，晚上給你燉魚湯。\n\n"
        "1-3 臥室 日/內\n"
        "人物：妻子\n"
        "△妻子低頭看著空空的手心，眼眶泛紅，雙手輕輕護住隆起的腹部，眼淚滴在針織衫上。\n"
        "妻子（輕聲）：寶寶，媽媽是不是很沒用啊。\n"
    )
    c5_s1 = {
        "project_id": "case05-project",
        "episode_id": "EP01",
        "scene_id": "EP01-S01",
        "source_refs": ["ch05:u2_bedroom"],
        "adaptation_mode": "balanced",
        "setting": {"location": "bedroom", "time": "day", "interior": True, "timeline_tag": "present"},
        "characters": ["wife"],
        "scene_goal": "妻子發現五百元遺失並翻找口袋",
        "dramatic_turn": "翻遍外套口袋確認錢已遺失",
        "dialogue": [{"speaker": "wife", "text": "不可能啊……我明明裝兜里了。", "audio_type": "onscreen"}],
        "props": ["khaki_coat"],
        "continuity_initial": {"money_500": "missing"},
        "continuity_final": {"money_500": "missing"},
        "estimated_duration_seconds": {"min": 8, "max": 13},
        "adaptation_changes": [
            {"type": "reorder", "description": "以臥室找錢的焦急狀態開場，再切入菜市場（閃回）交代掉錢過程，並刪去原版首句重複畫外音", "source_ref": "ch05:u2_bedroom"}
        ],
        "storyboard_handoff": {
            "recommended_generation_modes": ["I2V"],
            "required_visual_beats": ["倒出皮包收據", "翻出空外套口袋"],
            "required_audio_beats": ["衣物翻找摩擦聲"],
            "must_preserve": ["孕肚特徵與空口袋"],
        },
    }
    c5_s2 = {
        "project_id": "case05-project",
        "episode_id": "EP01",
        "scene_id": "EP01-S02",
        "source_refs": ["ch05:u1_market"],
        "adaptation_mode": "balanced",
        "setting": {"location": "wet_market", "time": "day", "interior": False, "timeline_tag": "flashback"},
        "characters": ["wife", "husband"],
        "scene_goal": "閃回展示菜市場接電話時錢滑落地面",
        "dramatic_turn": "溫馨通話與鈔票掉落地面形成戲劇反諷",
        "dialogue": [
            {"speaker": "husband", "text": "慢點走，別買太重的。", "audio_type": "phone"},
            {"speaker": "wife", "text": "知道了，晚上給你燉魚湯。", "audio_type": "onscreen"},
        ],
        "props": ["money_500", "pink_phone"],
        "continuity_initial": {"money_500": "in_pocket"},
        "continuity_final": {"money_500": "on_wet_ground"},
        "estimated_duration_seconds": {"min": 10, "max": 16},
        "adaptation_changes": [
            {"type": "must_keep", "description": "顯式標記（閃回）保護時間線因果", "source_ref": "ch05:u1_market"}
        ],
        "storyboard_handoff": {
            "recommended_generation_modes": ["I2V"],
            "required_visual_beats": ["拎菜接電話微笑", "鈔票滑落濕地特寫"],
            "required_audio_beats": ["菜市場環境音", "電話溫柔男聲"],
            "must_preserve": ["鈔票掉在濕水泥地上未被察覺"],
        },
    }
    c5_s3 = {
        "project_id": "case05-project",
        "episode_id": "EP01",
        "scene_id": "EP01-S03",
        "source_refs": ["ch05:u2_bedroom"],
        "adaptation_mode": "balanced",
        "setting": {"location": "bedroom", "time": "day", "interior": True, "timeline_tag": "present"},
        "characters": ["wife"],
        "scene_goal": "回到臥室現實時間線完成情緒沉澱",
        "dramatic_turn": "自責落淚撫摸孕肚",
        "dialogue": [{"speaker": "wife", "text": "寶寶，媽媽是不是很沒用啊。", "audio_type": "onscreen"}],
        "props": ["khaki_coat"],
        "continuity_initial": {"money_500": "missing"},
        "continuity_final": {"money_500": "missing"},
        "estimated_duration_seconds": {"min": 6, "max": 10},
        "adaptation_changes": [],
        "storyboard_handoff": {
            "recommended_generation_modes": ["I2V"],
            "required_visual_beats": ["雙手護住孕肚落淚"],
            "required_audio_beats": ["安靜室內輕微啜泣聲"],
            "must_preserve": ["溫情傷感基調，不強行塞入打臉反轉"],
        },
    }
    cases.append({
        "case_id": "case05_emotional_no_combat",
        "source": c5_source,
        "script": c5_script,
        "handoff": make_valid_handoff("case05-project", "healing_literary", "9:16", [c5_s1, c5_s2, c5_s3]),
    })

    # Case 06: 激烈戰鬥（目標、行動、結果及 AI 低碰撞可拍性）
    c6_source = {
        "case_id": "case06_intense_combat",
        "title": "激烈戰鬥（戰術目標、代價與 AI 低碰撞拆解）",
        "genre_mode": "wuxia_action",
        "story_units": [
            {"unit_id": "ch06:u1_fight", "summary": "林澈左臂帶傷在窄巷攔截趙坤，以折斷短刀為代價奪回帳冊", "expected_grade": "MUST_KEEP"}
        ],
    }
    c6_script = (
        "第01集｜斷刃\n\n"
        "1-1 青石窄巷 夜/外\n"
        "人物：林澈、趙坤\n"
        "△雨夜窄巷，趙坤右手緊護懷中油布帳冊，左手鐵爪直取林澈咽喉。\n"
        "△林澈不退反進，任由鐵爪劃破自己左袖滲出鮮血，右手短刀精準卡入鐵爪關節縫隙，猛力一擰。\n"
        "△寒光迸裂，短刀應聲折斷，半截斷刃擦過趙坤手背，油布帳冊脫手飛出，落入林澈左手。\n"
        "趙坤（捂住流血手背，後退）：你瘋了！拿命換一本死帳？\n"
        "林澈（將斷刀插進青石縫，喘息）：死人的帳，才最貴。\n"
    )
    c6_scene = dict(
        c1_scene,
        project_id="case06-project",
        source_refs=["ch06:u1_fight"],
        characters=["lin-che", "zhao-kun"],
    )
    c6_scene["storyboard_handoff"] = {
        "recommended_generation_modes": ["FL2V", "I2V"],
        "required_visual_beats": ["鐵爪破袖滲血", "短刀卡入關節折斷寒光", "奪回油布帳冊定格"],
        "required_audio_beats": ["金屬崩裂聲", "雨水落地聲"],
        "must_preserve": ["左袖受傷與短刀折斷的戰術代價"],
        "production_risk": {
            "level": "high",
            "reason": "雙人近身兵刃交擊直接生成易穿模",
            "original_vision": "雙人全身纏鬥十招奪冊",
            "simplified_alternative": "拆為三鏡：①趙坤突刺起手(I2V) -> ②刀刃卡住鐵爪崩斷特寫(FL2V) -> ③林澈接住帳冊、趙坤捂手後退結果(I2V)",
        },
    }
    cases.append({
        "case_id": "case06_intense_combat",
        "source": c6_source,
        "script": c6_script,
        "handoff": make_valid_handoff("case06-project", "wuxia_action", "9:16", [c6_scene]),
    })

    # Case 07: 9:16 / 16:9 相同情節雙畫幅適配
    c7_source = {
        "case_id": "case07_aspect_ratio_9x16_vs_16x9",
        "title": "9:16 與 16:9 相同情節（因果不變，空間與分鏡要求適配）",
        "genre_mode": "mystery_thriller",
        "story_units": c1_source["story_units"],
    }
    c7_scene_16x9 = dict(c1_scene, project_id="case07-project")
    c7_scene_16x9["storyboard_handoff"] = {
        "recommended_generation_modes": ["Ref2V", "I2V"],
        "required_visual_beats": [
            "16:9 橫屏構圖：左側火盆與林澈，右側陰影中的木門與門縫透光，形成水平空間張力",
            "信紙背面浮現字跡特寫",
        ],
        "required_audio_beats": ["三下敲門聲", "門外畫外音"],
        "must_preserve": ["信背字跡與門內外空間對峙"],
    }
    cases.append({
        "case_id": "case07_aspect_ratio_9x16_vs_16x9",
        "source": c7_source,
        "script": c1_script,
        "handoff": make_valid_handoff("case07-project", "mystery_thriller", "16:9", [c7_scene_16x9]),
    })

    # Case 08: 來源資料不完整（殘稿標明缺口，不虛構後續）
    c8_source = {
        "case_id": "case08_incomplete_source",
        "title": "來源資料不完整（殘稿標明缺口，禁止擅自虛構結局）",
        "genre_mode": "mystery_thriller",
        "is_incomplete": True,
        "story_units": [
            {"unit_id": "ch08:u1_incomplete", "summary": "林澈打開暗格發現半枚銅鑰匙（原稿至此中斷，缺下半章）", "expected_grade": "MUST_KEEP"}
        ],
    }
    c8_script = (
        "第01集｜半枚銅鑰\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈\n"
        "△林澈撬開桌底暗格，指尖從灰燼中拈起半枚斷裂的青銅鑰匙。\n"
        "林澈（低頭凝視斷口）：只剩一半……另一半在誰手裡？\n"
    )
    c8_scene = dict(
        c1_scene,
        project_id="case08-project",
        source_refs=["ch08:u1_incomplete"],
        characters=["lin-che"],
    )
    c8_issues = [
        {
            "issue_id": "gap-01",
            "type": "incomplete_source",
            "source_refs": ["ch08:u1_incomplete"],
            "description": "原稿於發現半枚銅鑰匙處中斷，後續銅鎖位置與真兇身份缺失",
            "resolution": "於懸念處收束本集，顯式標記缺口待作者補充，絕不自行捏造真兇",
        }
    ]
    cases.append({
        "case_id": "case08_incomplete_source",
        "source": c8_source,
        "script": c8_script,
        "handoff": make_valid_handoff("case08-project", "mystery_thriller", "9:16", [c8_scene], source_issues=c8_issues),
    })

    # Case 09: 長篇多集跨集連戲（驗證跨集道具與狀態機連貫）
    c9_source = {
        "case_id": "case09_multi_episode_continuity",
        "title": "長篇多集跨集連戲（道具狀態、角色傷勢與 Debt Ledger 跨集傳遞）",
        "genre_mode": "mystery_thriller",
        "story_units": [
            {"unit_id": "ch09:ep1", "summary": "第1集林澈拿到濕信封並翻開背面", "expected_grade": "MUST_KEEP"},
            {"unit_id": "ch09:ep2", "summary": "第2集林澈手持同一封濕信與進門的沈寧對質", "expected_grade": "MUST_KEEP"},
        ],
    }
    c9_script = (
        "第01集｜回信\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧\n"
        "△桌上放著一封被水浸濕的信。林澈拿起信翻至背面，門外傳來敲門聲。\n"
        "沈寧（門外）：開門。我知道你看過那封信。\n"
        "林澈：這字……不是我寫的。\n\n"
        "2-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧\n"
        "△木門推開，沈寧走入客廳。林澈右手仍緊握著那封背面朝上的濕信。\n"
        "沈寧：把信給我，否則趙坤的人馬上到。\n"
        "林澈：先告訴我，背面這行紅字是誰留的。\n"
    )
    c9_ep1_sc = dict(
        c1_scene,
        project_id="case09-project",
        episode_id="EP01",
        scene_id="EP01-S01",
        source_refs=["ch09:ep1"],
        continuity_initial={"wet_letter": "on_table"},
        continuity_final={"wet_letter": "in_lin_che_hand"},
    )
    c9_ep2_sc = dict(
        c1_scene,
        project_id="case09-project",
        episode_id="EP02",
        scene_id="EP02-S01",
        source_refs=["ch09:ep2"],
        continuity_initial={"wet_letter": "in_lin_che_hand"},
        continuity_final={"wet_letter": "held_between_both"},
    )
    c9_eps = [
        {
            "episode_id": "EP01",
            "title": "回信",
            "target_duration_seconds": 18,
            "episode_goal": "發現信件異常",
            "act_out_type": "revelation_twist",
            "scenes": [c9_ep1_sc],
        },
        {
            "episode_id": "EP02",
            "title": "對質",
            "target_duration_seconds": 18,
            "episode_goal": "當面追問字跡來源",
            "act_out_type": "jeopardy_cliffhanger",
            "scenes": [c9_ep2_sc],
        },
    ]
    cases.append({
        "case_id": "case09_multi_episode_continuity",
        "source": c9_source,
        "script": c9_script,
        "handoff": make_valid_handoff("case09-project", "mystery_thriller", "9:16", [], episodes_override=c9_eps),
    })

    # Case 10: 刻意矛盾原文（主動提出矛盾清單而非悄悄修復）
    c10_source = {
        "case_id": "case10_contradictory_source",
        "title": "刻意矛盾原文（主動登記矛盾清單與解決方案）",
        "genre_mode": "mystery_thriller",
        "known_contradictions": [
            "第1段稱林澈天生雙目失明，第3段卻寫林澈親眼看見信紙背面的紅色小字"
        ],
        "story_units": [
            {"unit_id": "ch10:u1_contra", "summary": "原文前稱盲眼後稱親眼看信", "expected_grade": "MUST_KEEP"}
        ],
    }
    c10_script = (
        "第01集｜盲紋\n\n"
        "1-1 舊公寓客廳 夜/內\n"
        "人物：林澈、沈寧\n"
        "△林澈雙目微闔，右手食指指腹沿著信紙背面凸起的針刺盲紋緩緩摸過，指尖突然停住。\n"
        "沈寧（門外）：我知道你摸出信背的字了。\n"
        "林澈：這針刺的筆跡……不是我留的。\n"
    )
    c10_scene = dict(
        c1_scene,
        project_id="case10-project",
        source_refs=["ch10:u1_contra"],
    )
    c10_issues = [
        {
            "issue_id": "contra-01",
            "type": "canon_contradiction",
            "source_refs": ["ch10:u1_contra"],
            "description": "原著第1段設定林澈雙目失明，第3段卻寫他『親眼看見信背紅字』，構成內部設定矛盾",
            "resolution": "主動登記矛盾，並將『看見紅字』改寫為『指腹摸出信背凸起的針刺盲紋』以統一盲人設定",
        }
    ]
    cases.append({
        "case_id": "case10_contradictory_source",
        "source": c10_source,
        "script": c10_script,
        "handoff": make_valid_handoff("case10-project", "mystery_thriller", "9:16", [c10_scene], source_issues=c10_issues),
    })

    return cases


def run_ab_comparison(bible: Dict[str, Any]) -> Dict[str, Any]:
    """
    進行 A/B 實測：對照「原始滿血版提示詞」與「新 novel-to-manju Skill」
    包含兩組典型測試：
    Experiment 1: 原提示詞自帶的「孕婦丟失500元」範例 vs 新 Skill 修復版
    Experiment 2: 懸疑小說「回信（含跨章伏筆與原文矛盾）」在「滿血版強迫爽點提示詞」下的劣化輸出 vs 新 Skill 輸出
    """
    # Exp 1: 原始《热门小说 改编剧本 【满血版】.txt》L40-60 原始劇本輸出
    legacy_exp1_script = (
        "1-1卧室日/内\n"
        "人物：妻子\n"
        "△怀孕7个月的妻子身穿白色孕妇装和米色针织开衫，坐在略显凌乱的床边，神色焦急地在棕色皮包和衣物堆里翻找。\n"
        "妻子（画外音）：我怀孕7个月那天弄丢了500块。\n"
        "△妻子在床尾翻找着一个黑色包包仔细检查，随后有些困惑地轻轻摇头。\n"
        "妻子：不可能啊。\n"
        "△接着妻子又抓起一件卡其色外套检查口袋，然后用力抖了抖，慌乱地翻找放在床上的包包和衣物。\n"
        "妻子：我明明装兜里了。\n"
        "△妻子微微低头，双眼无神地盯着下方，眼眶泛红。\n"
        "△妻子双手轻轻抚摸着自己隆起的腹部，微微低下头闭上眼睛，眼泪顺着脸颊流下，身体微微蜷缩。\n"
        "妻子：宝宝，妈妈是不是很没用啊。\n\n"
        "1-2菜市场日/外\n"
        "人物：妻子 丈夫\n"
        "△清晨人来人往的菜市场里，妻子左手拎着一袋蔬菜，低头看着自己隆起的肚子，步履缓慢地行走。\n"
        "△妻子右手拿着一部粉色手机接听电话，脸上露出温柔的笑容。\n"
        "丈夫（电话音）：慢点啊，别买太重的。\n"
        "妻子：知道了。\n"
        "△在妻子前方，几张粉红色的百元大钞散落在湿漉漉的水泥地面上。\n"
        "△妻子微笑着讲电话并向前走去，完全没有注意到脚下掉落的钱。\n"
        "妻子：晚上给你炖鱼汤。\n"
    )
    # 舊版因為要求「只输出剧本内容，不要附加任何解释」，無 Handoff，且 1-1 已丟錢，1-2 卻未標閃回又回到掉錢瞬間
    legacy_exp1_handoff = {
        "project_id": "legacy-exp1",
        "rights_status": "unconfirmed",
        "adaptation_mode": "balanced",
        "genre_mode": "healing_literary",
        "aspect_ratio": "9:16",
        "target_medium": "ai_animation",
        "episodes": [
            {
                "episode_id": "EP01",
                "title": "無標題",
                "target_duration_seconds": 90,
                "episode_goal": "未定義",
                "act_out_type": "meaningful_silence",
                "scenes": [
                    {
                        "project_id": "legacy-exp1",
                        "episode_id": "EP01",
                        "scene_id": "EP01-S01",
                        "source_refs": ["ch05:u2_bedroom"],
                        "adaptation_mode": "balanced",
                        "setting": {"location": "bedroom", "time": "day", "interior": True, "timeline_tag": "present"},
                        "characters": ["wife"],
                        "scene_goal": "找錢",
                        "dramatic_turn": "找不到",
                        "dialogue": [],
                        "props": ["money_500"],
                        "continuity_initial": {"money_500": "missing"},
                        "continuity_final": {"money_500": "missing"},
                        "estimated_duration_seconds": {"min": 15, "max": 22},
                        "adaptation_changes": [],
                        "storyboard_handoff": {"required_visual_beats": [], "required_audio_beats": [], "must_preserve": []},
                    },
                    {
                        "project_id": "legacy-exp1",
                        "episode_id": "EP01",
                        "scene_id": "EP01-S02",
                        "source_refs": ["ch05:u1_market"],
                        "adaptation_mode": "balanced",
                        "setting": {"location": "market", "time": "day", "interior": False, "timeline_tag": "present"},
                        "characters": ["wife", "husband"],
                        "scene_goal": "掉錢",
                        "dramatic_turn": "掉錢",
                        "dialogue": [],
                        "props": ["money_500"],
                        "continuity_initial": {"money_500": "in_pocket"},
                        "continuity_final": {"money_500": "on_ground"},
                        "estimated_duration_seconds": {"min": 12, "max": 18},
                        "adaptation_changes": [],
                        "storyboard_handoff": {"required_visual_beats": [], "required_audio_beats": [], "must_preserve": []},
                    },
                ],
            }
        ],
    }

    # Exp 2: 當嚴格執行「滿血版」L8-22 指令（開篇3秒爆點、每80字小爽點、每200字大爽點、全程不憋屈）改編懸疑小說時的典型劣化劇本
    legacy_exp2_script = (
        "1-1舊公寓夜/內\n"
        "人物：阿澈、沈寧、趙坤\n"
        "△特寫鏡頭推鏡頭給到阿澈，他心裡想著這封信的秘密，百感交集。\n"
        "阿澈（畫外音）：我其實是隱藏的百億神豪，今天三年之期已到，誰敢惹我我就讓他下跪求饒！\n"
        "△趙坤一腳踹開門衝進來囂張大笑，沈寧也在旁邊亮出她其實是礦長孤女的真實身份。\n"
        "趙坤：你算什麼東西也配拿這封信？還不快給我下跪求饒，否則我立刻把你拉出去餵狗并且徹底碾壓你們全家所有人的性命財產！\n"
        "△阿澈冷笑一聲直接一巴掌扇耳光把趙坤抽飛十米遠，當場展現仙帝附體般的恐怖實力完成逆襲打臉。\n"
        "阿澈（畫外音）：這就是得罪我的下場，下一秒還有更驚天的秘密即將揭曉！\n"
    )
    legacy_exp2_source = {
        "case_id": "ab_exp2_mystery",
        "genre_mode": "mystery_thriller",
        "is_incomplete": True,
        "known_contradictions": ["原稿前後時間矛盾"],
        "story_units": [
            {"unit_id": "ch01:u1", "summary": "林澈發現信背字跡遭篡改", "expected_grade": "MUST_KEEP"},
            {"unit_id": "ch01:u2", "summary": "沈寧門外試探", "expected_grade": "MUST_KEEP"},
        ],
        "foreshadowing": [
            {"clue_id": "clue-01", "min_reveal_scene_index": 2, "forbidden_early_spoiler_phrases": ["礦長孤女"]}
        ],
    }
    legacy_exp2_handoff = {
        "project_id": "legacy-exp2",
        "rights_status": "unconfirmed",
        "adaptation_mode": "balanced",
        "genre_mode": "mystery_thriller",
        "aspect_ratio": "9:16",
        "target_medium": "ai_animation",
        "episodes": [
            {
                "episode_id": "EP01",
                "title": "打臉",
                "target_duration_seconds": 90,
                "episode_goal": "爽點拉滿",
                "act_out_type": "jeopardy_cliffhanger",
                "scenes": [
                    {
                        "project_id": "legacy-exp2",
                        "episode_id": "EP01",
                        "scene_id": "EP01-S01",
                        "source_refs": [],
                        "adaptation_mode": "balanced",
                        "setting": {"location": "old_apartment", "time": "night", "interior": True, "timeline_tag": "present"},
                        "characters": ["lin-che", "shen-ning", "zhao-kun"],
                        "scene_goal": "打臉趙坤",
                        "dramatic_turn": "扇耳光",
                        "dialogue": [
                            {"speaker": "lin-che", "text": "我其實是礦長孤女的保護人", "audio_type": "voiceover"}
                        ],
                        "props": [],
                        "continuity_initial": {},
                        "continuity_final": {},
                        "estimated_duration_seconds": {"min": 15, "max": 25},
                        "adaptation_changes": [],
                        "storyboard_handoff": {"required_visual_beats": [], "required_audio_beats": [], "must_preserve": []},
                    }
                ],
            }
        ],
    }

    cases = build_test_cases()
    c5 = next(c for c in cases if c["case_id"] == "case05_emotional_no_combat")
    c1 = next(c for c in cases if c["case_id"] == "case01_high_density_low_event")

    exp1_legacy_eval = evaluate_adaptation(c5["source"], legacy_exp1_handoff, legacy_exp1_script, bible)
    exp1_new_eval = evaluate_adaptation(c5["source"], c5["handoff"], c5["script"], bible)

    exp2_legacy_eval = evaluate_adaptation(legacy_exp2_source, legacy_exp2_handoff, legacy_exp2_script, bible)
    exp2_new_eval = evaluate_adaptation(c1["source"], c1["handoff"], c1["script"], bible)

    return {
        "experiment_1_pregnant_wife_500_yuan": {
            "description": "對照原始提示詞自帶的『孕婦丟500元』範例 vs 新 Skill 修復版",
            "legacy_prompt_result": exp1_legacy_eval,
            "novel_to_manju_result": exp1_new_eval,
        },
        "experiment_2_mystery_thriller_adaptation": {
            "description": "對照原始提示詞強制『3秒爆點+80字爽點+全程不憋屈』改編懸疑小說 vs 新 Skill 改編版",
            "legacy_prompt_result": exp2_legacy_eval,
            "novel_to_manju_result": exp2_new_eval,
        },
    }


def main() -> int:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)

    bible = make_base_bible()
    bible_path = FIXTURES_DIR / "story_bible.json"
    bible_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")

    schema_path = SKILL_ROOT.parent.parent / "references" / "adapt" / "templates" / "handoff.schema.json"
    schema_data = json.loads(schema_path.read_text(encoding="utf-8"))

    cases = build_test_cases()
    summary_results = []
    all_passed = True

    print("=================================================================")
    print("  Novel-to-Manju MVP v1.0 — 10 大邊界測試案例與 A/B 對照實測")
    print("=================================================================")

    for case in cases:
        cid = case["case_id"]
        c_dir = FIXTURES_DIR / cid
        c_dir.mkdir(parents=True, exist_ok=True)

        src_file = c_dir / "source.json"
        scr_file = c_dir / "script.md"
        hnd_file = c_dir / "handoff.json"

        src_file.write_text(json.dumps(case["source"], ensure_ascii=False, indent=2), encoding="utf-8")
        scr_file.write_text(case["script"], encoding="utf-8")
        hnd_file.write_text(json.dumps(case["handoff"], ensure_ascii=False, indent=2), encoding="utf-8")

        # 執行 Schema 驗證 + 四大腳本邏輯驗證
        schema_errs = validate_json_against_schema(case["handoff"], schema_data)
        eval_res = evaluate_adaptation(case["source"], case["handoff"], case["script"], bible)
        eval_res["schema_errors"] = schema_errs
        if schema_errs:
            eval_res["status"] = "FAIL"

        exp_file = EXPECTED_DIR / f"{cid}_result.json"
        exp_file.write_text(json.dumps(eval_res, ensure_ascii=False, indent=2), encoding="utf-8")

        passed = eval_res["status"] == "PASS"
        if not passed:
            all_passed = False

        print(
            f"[{eval_res['status']}] {cid:<36} | 得分: {eval_res['total_score_100']:>5.1f}/100 | "
            f"閘門觸發: {len(eval_res['gate_failures'])} | 錯誤: {eval_res['error_count']}"
        )
        summary_results.append({"case_id": cid, "title": case["source"]["title"], **eval_res})

    ab_results = run_ab_comparison(bible)
    ab_output = {
        "suite_status": "PASS" if all_passed else "FAIL",
        "boundary_cases_count": len(summary_results),
        "boundary_cases": summary_results,
        "ab_comparison": ab_results,
    }
    ab_file = EXPECTED_DIR / "ab_test_results.json"
    ab_file.write_text(json.dumps(ab_output, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n-----------------------------------------------------------------")
    print("  A/B 測試結果摘要（原始滿血版提示詞 vs. Novel-to-Manju v1.0）")
    print("-----------------------------------------------------------------")
    for exp_key, exp_val in ab_results.items():
        leg = exp_val["legacy_prompt_result"]
        new = exp_val["novel_to_manju_result"]
        print(f"* {exp_key}:")
        print(
            f"  - 原始滿血版提示詞: 狀態={leg['status']} | 總分={leg['total_score_100']}/100 | "
            f"觸發閘門={leg['gate_failures']} | 錯誤數={leg['error_count']}"
        )
        print(
            f"  - Novel-to-Manju:   狀態={new['status']} | 總分={new['total_score_100']}/100 | "
            f"觸發閘門={new['gate_failures']} | 錯誤數={new['error_count']}"
        )

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
