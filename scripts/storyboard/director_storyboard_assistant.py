#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 電影與漫劇導演分鏡、鏡頭光學與多模型原生編譯輔助工具 (v2.0)
零外部依賴，整合：
1. 焦距 × 物理物距光學本質 (24mm <0.5m 近距拉伸 vs 100mm >6m 遠距壓縮)
2. 視角與遮擋三路動態路由 (Dirty Frame 20-35% 偷窺 | 武戲 90° 垂直無遮擋 | 對白 OTS 反應藏拙)
3. 畫幅幾何自適應 (16:9 橫屏三分展開 vs 9:16 直式縱深交錯與 UI 安全區)
4. 台詞 100% 保真與四維配音氣口順延計算
5. Layer 1/2/3 三層分離與多模型原生編譯器 (Seedance 2.0 自然流 / MiniMax H3 三欄 <d> / Kling 首尾幀 / 漫劇九宮格鎖臉)
   影片模型輸出一律只用色名＋物件（不含 HEX）；HEX 只保留在 Layer 1 導演卡與九宮格（圖像模型）。
"""

import argparse
import io
import json
import re
import sys

# 確保 Windows 終端輸出 UTF-8
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

LENS_OPTICS_PRESETS = {
    "24mm": {
        "name": "24mm 超廣角 (臨場參與者)",
        "distance": "物距極近 (<0.4m)，攝影機貼身逼近主體，主角面部嚴格鎖在內圈 60% 安全區防邊緣畸變",
        "distance_en": "24mm ultra-wide lens placed extremely close (<0.4m) to the subject, keeping facial features within the center 60% safe zone",
        "spatial": "強化極致近大遠小，背景顯得極小極遠，地表與空間線條快速向遠處劇烈匯聚拉伸",
        "spatial_en": "exaggerating near-far perspective with strong converging lines rushing into the deep background, deep depth of field f/11",
        "psychology": "身臨其境的壓迫感、參與者視角、動態視覺衝擊拉滿"
    },
    "35mm": {
        "name": "35mm 廣角人文 (沉浸敘事)",
        "distance": "物距約 1.2m~1.5m，維持微近身在場視角",
        "distance_en": "35mm wide-normal lens at 1.2m distance",
        "spatial": "微弱透視延伸，兼顧人物上半身神態與周遭實體家具空間交代，比例舒展",
        "spatial_en": "natural spatial perspective balancing character performance and environmental context",
        "psychology": "沉浸式陪伴者、現代電影最通用的敘事黃金焦段"
    },
    "50mm": {
        "name": "50mm 標準中焦 (客觀見證者)",
        "distance": "物距約 2.0m~2.5m，自然人眼社交距離",
        "distance_en": "50mm standard prime lens at 2.0m eye-level distance",
        "spatial": "真實人眼透視，前後景比例完全忠實於物理現實，無光學畸變，中度柔和虛化",
        "spatial_en": "true-to-life human eye perspective with zero optical distortion and moderate depth of field f/4.0",
        "psychology": "客觀見證者、平實、值得信賴、生活化真實"
    },
    "85mm": {
        "name": "85mm 人像長焦 (情感聚焦)",
        "distance": "物距約 3.5m~5.0m，攝影機適度退後",
        "distance_en": "85mm portrait telephoto lens positioned 4 meters away",
        "spatial": "淺景深 f/2.0 刀鋒虛化，背景柔和散焦成奶油光斑並保留色卡色階，人物輪廓立體分離",
        "spatial_en": "shallow depth of field f/2.0 isolating the subject, background bokeh retaining the scene's warm/cool color palette",
        "psychology": "深情凝視、情緒微表情高度聚焦"
    },
    "100mm": {
        "name": "100mm 望遠長焦 (疏離觀察者)",
        "distance": "物距 >6.0m (6~10m)，攝影機遠離主體進行遠距離狙擊調度",
        "distance_en": "100mm telephoto lens positioned 8 meters away across the space",
        "spatial": "極致空間壓縮感，遠處背景被巨幅放大並拉平緊貼在主體腦後如平面幕布，極淺景深 f/1.4",
        "spatial_en": "extreme telephoto spatial compression flattening the background directly against the subject's profile with razor-thin depth of field f/1.4",
        "psychology": "冷酷審視、暗中窺探、命運被監視的宿命窒息感"
    }
}

POV_MODES = {
    "objective": {
        "name": "客觀紀錄視角 (Objective View)",
        "desc": "攝影機處於第三人稱客觀位置，平穩端正，嚴守 180 度軸線記錄主體連續動作",
        "desc_en": "third-person objective camera maintaining strict 180-degree axis"
    },
    "dirty_frame": {
        "name": "前景遮擋主觀偷窺視角 (Dirty Frame POV 20%-35%)",
        "desc": "攝影機置於半掩門框、百葉窗欞或暗處障礙物後方，前景重度失焦遮擋畫面側邊 25%~30%（黃金面積比），形成暗中窺視獵物的極致懸疑危險感",
        "desc_en": "voyeuristic dirty-frame POV shot through a half-closed door frame obstructing 30% of the foreground in heavy blur"
    },
    "reflection_delay": {
        "name": "鏡面/水杯倒影屏息延遲 (Reflection Suspense Delay)",
        "desc": "運鏡驟然由快轉慢，前 1.5 秒焦點死死鎖定於玻璃水杯或鏡面微弱反光中，倒映出突發危險人影，阻斷觀眾預期製造心跳驟停，隨後再切至主體反應",
        "desc_en": "breath-holding suspense delay focusing first on the quivering water glass reflection revealing a dark silhouette before shifting focus to the subject"
    },
    "clear_impact_90deg": {
        "name": "武戲 90° 垂直軸線無遮擋視角 (90° Perpendicular Clear Impact)",
        "desc": "【強制撤除一切前景遮擋】機位嚴格垂直於發力軸線（90度正側面或45度全開側面），遵循蓄力➔出擊➔接觸➔反應四步走，讓碰撞接觸點、火花與受力後滑在畫面中央 100% 無遮擋展開",
        "desc_en": "90-degree perpendicular side profile with ZERO foreground obstruction, clearly exposing the exact point of physical impact, sparks, and recoil"
    },
    "defensive_ots": {
        "name": "防禦性過肩反應藏拙視角 (Defensive Reaction OTS)",
        "desc": "說話者處於前景暗部虛化肩背位（佔畫幅 25%，保持輕微呼吸起伏保活），焦點銳利鎖定在聽者的前側 45 度面部微表情反應，規避長句正臉口型崩壞",
        "desc_en": "over-the-shoulder shot past the speaker's blurred foreground shoulder (with subtle breathing motion), focusing sharply on the listener's 3/4 profile reaction"
    }
}

BUILT_IN_PRESETS = {
    "suspense_interrogation": {
        "title": "懸疑密室窺視 (100mm 遠距空間壓縮 + Dirty Frame 30% + 屏息延遲)",
        "focal": "100mm",
        "pov": "dirty_frame",
        "aspect": "16:9",
        "duration": 4.0,
        "dirty_frame_obj": "半掩的生鏽鐵門框與百葉窗暗影",
        "anchor_obj": "【舊木審訊桌】與【玻璃水杯】",
        "subject": "神色緊繃的調查員",
        "action": "前1.5秒聚焦於桌面上微微震顫的玻璃水杯倒影，隨後焦點切向調查員，他翻找卷宗的雙手驟然僵在半空，五指猛然收緊將紙張捏出折痕",
        "expression": "瞳孔微縮，下頜線條驟然咬緊，額角滑落一滴冷汗",
        "micro_tail": "風衣衣領隨急促吸氣微微起伏，桌角灰塵在冷光中微浮",
        "palette": "冷鋼夜黑 (#0A0E17 深夜藍牆面 + #18233C 冷灰環境光 + #D4AF37 暖金檯燈光)",
        "speaker": "調查員",
        "dialogue": "誰在那裡？出來！",
        "voice_4d": "壓抑戰慄低音，聲帶緊繃，在『誰在那裡』後窒息般停住一口氣，句尾低沉切斷",
        "sfx": "紙張揉皺聲驟停、低頻空調嗡鳴、沉重的木地板踩踏聲"
    },
    "epic_wasteland": {
        "title": "廢土史詩衝擊 (24mm <0.4m 極近物距空間拉伸 + 低機位仰拍)",
        "focal": "24mm",
        "pov": "objective",
        "aspect": "16:9",
        "duration": 4.0,
        "dirty_frame_obj": "無",
        "anchor_obj": "【龜裂荒漠岩地】與【巨型生鏽機甲殘骸】",
        "subject": "身披破舊斗篷的獨行旅人",
        "action": "旅人沉重的戰靴踏碎前景龜裂地面，揚起乾燥沙塵，隨即拔出腰間長刀指向遠方天際線",
        "expression": "眼神冷冽堅定，雙唇緊閉（全身/廣角不強調細碎五官，突出剪影張力）",
        "micro_tail": "破舊斗篷下擺與沙塵在狂風中劇烈向後獵獵飛揚",
        "palette": "末日黃沙 (#1A1412 焦黑岩壁 + #8C5A32 赭石沙塵 + #F2A950 烈日琥珀光)",
        "speaker": "",
        "dialogue": "",
        "voice_4d": "無台詞（環境風聲主導）",
        "sfx": "戰靴踏碎岩石聲、金屬長刀出鞘清脆鳴響、荒原狂風呼嘯聲"
    },
    "wong_kar_wai_noir": {
        "title": "王家衛港風暗室 (85mm 淺景深 + 雨滴窗櫺遮擋 + 四維氣音配音)",
        "focal": "85mm",
        "pov": "dirty_frame",
        "aspect": "9:16",
        "duration": 4.5,
        "dirty_frame_obj": "掛滿雨滴的茶餐廳玻璃窗櫺與霓虹散焦光斑",
        "anchor_obj": "【復古綠皮卡座】與【滿溢的白瓷茶杯】",
        "subject": "身穿墨綠旗袍的女主角",
        "action": "前1.5秒特寫白瓷茶杯中茶水緩緩滿溢流過桌沿，隨後焦點移向卡座上的女主角，她指尖輕輕拉動天鵝絨窗簾，緩緩抬眼望向對面",
        "expression": "眼眶微紅泛著水光，嘴角微微下撇，下唇微顫",
        "micro_tail": "百葉窗切片光在旗袍領口微晃，耳墜與碎髮隨輕嘆微微搖曳",
        "palette": "王家衛復古綠金 (#050B08 墨黑陰影 + #0D2818 暗綠卡座皮面 + #E5A93C 琥珀金茶杯光)",
        "speaker": "女主角",
        "dialogue": "你還記得……我們第一次見面的地方嗎？",
        "voice_4d": "細膩溫潤氣音，聲帶只微微閉合、氣息偏多，在『你還記得』後猶豫停頓一拍，句尾微挑帶嘆息",
        "sfx": "窗外淅瀝雨聲、茶水滴落桌面聲、老舊吊扇低轉聲"
    },
    "combat_impact_90deg": {
        "title": "高速武戲破盾 (50mm 90°垂直無遮擋 + 蓄力出擊打擊反應四步走)",
        "focal": "50mm",
        "pov": "clear_impact_90deg",
        "aspect": "16:9",
        "duration": 3.5,
        "dirty_frame_obj": "無（武戲強制 0% 遮擋）",
        "anchor_obj": "【青石板地面】與【重型合金盾牌】",
        "subject": "@角色A (黑衣拳師) 與 @角色B (持盾重甲衛士)",
        "action": "1.前腳蹬地碎石飛濺蓄力 ➔ 2.轉腰帶肩右拳極速水平轟出 ➔ 3.拳面以90度無遮擋視角垂直轟中B的金屬盾心迸發火花與環形氣浪 ➔ 4.盾牌後偏、B雙靴摩擦石地後滑半米犁出白痕 ➔ 5.A收拳回防降低重心",
        "expression": "A下頜咬緊眼神凌厲；B雙臂肌肉震顫、眉頭緊鎖，兩人雙唇均緊閉不說話",
        "micro_tail": "衝擊氣浪吹散地面煙塵，A的衣擺隨收勢動作自然回落，胸口劇烈起伏喘息",
        "palette": "冷鋼夜黑 (#080C14 極深夜幕 + #1C2D42 冷藍月光 + #FF6B35 撞擊火花橘光)",
        "speaker": "",
        "dialogue": "",
        "voice_4d": "無台詞（純物理打擊與呼吸音效）",
        "sfx": "鞋底蹬地爆裂聲、破空拳風、震耳欲聾的沉重金屬撞擊巨響、刺耳的戰靴刮地摩擦聲"
    },
    "anime_grid_9panel": {
        "title": "AI 漫劇 3x3 九宮格同空間鎖臉關鍵幀 (Stage A 資產生成)",
        "focal": "35mm",
        "pov": "objective",
        "aspect": "16:9",
        "duration": 12.0,
        "dirty_frame_obj": "Panel 2 含竹葉前景遮擋，Panel 5-6 武戲 0% 遮擋",
        "anchor_obj": "【雨夜竹林石階】與【青銅雲紋古劍】",
        "subject": "銀白高馬尾配暗紅髮帶、左眼角緋紅淚痣、玄黑窄袖勁裝劍客",
        "action": "Panel 1(24mm全景定場) ➔ Panel 2(Dirty Frame竹葉窺視) ➔ Panel 3(劍鍔水滴倒影延遲) ➔ Panel 4(拇指推劍出鞘一寸) ➔ Panel 5(90度側面拔劍突進) ➔ Panel 6(90度無遮擋刀劍交擊火花) ➔ Panel 7(對手滑退犁地) ➔ Panel 8(OTS過肩拍收劍滴水) ➔ Panel 9(100mm遠距壓縮對峙)",
        "expression": "全9格嚴格鎖定左眼角緋紅淚痣與冷峻劍客五官一致",
        "micro_tail": "雨水飛濺、竹葉飄落、高馬尾與衣袂隨劍氣擺動",
        "palette": "國風冷冽青金 (#080C14 墨黑夜幕 + #16302B 竹林地面暗青 + #64E8FF 劍氣青光 + #C92A2A 髮帶緋紅)",
        "speaker": "",
        "dialogue": "",
        "voice_4d": "Stage A 靜態九宮格關鍵幀出圖（無音訊）",
        "sfx": "Stage B 轉影片時注入雨聲與劍鳴"
    }
}


def parse_palette(text: str) -> tuple:
    """'冷鋼夜黑 (#0A0E17 深夜藍牆面 + #D4AF37 暖金檯燈光)' → ('冷鋼夜黑', [('#0A0E17', '深夜藍牆面'), ...])。"""
    title, _, body = text.partition("(")
    entries = []
    for part in body.rstrip(")").split("+"):
        m = re.match(r"\s*(#[0-9A-Fa-f]{6})\s*(.*?)\s*$", part)
        if m:
            entries.append((m.group(1), m.group(2)))
    return title.strip(), entries


HEX_RE = re.compile(r"#[0-9A-Fa-f]{6}(?![0-9A-Fa-f])")
VIDEO_MODELS = {"seedance-v8", "minimax-h3", "kling-fl2va"}  # 影片模型不收 HEX 色碼


def strip_hex(text: str) -> tuple:
    """#RRGGBB 換成「色票指定」，回傳 (文字, 替換次數)。"""
    return HEX_RE.subn("色票指定", text)


def palette_names(text: str) -> str:
    """影片模型用的色盤描述：只保留色名＋物件，去掉 HEX。"""
    title, entries = parse_palette(text)
    names = [name for _, name in entries if name]
    if not names:
        return title or text
    return f"{title}（{'、'.join(names)}）"


def check_dialogue_pacing(dialogue: str, duration: float, is_slow_mood: bool = True) -> dict:
    """檢查台詞字數是否超出當前鏡頭秒數的合理語速，並計算氣口順延點。"""
    clean_text = dialogue.strip()
    if not clean_text:
        return {"has_dialogue": False, "char_count": 0, "cps": 0.0, "overflow": False, "kept": "", "overflow_out": None}
    char_count = len(clean_text)
    max_cps = 2.8 if is_slow_mood else 3.8
    cps = round(char_count / max(duration, 0.5), 2)
    max_chars = int(duration * max_cps)
    if char_count > max_chars and char_count > 6:
        # 尋找標點或中間氣口切斷
        split_idx = max_chars
        for punct in ["，", "……", "—", "、", "；", " ", ","]:
            pos = clean_text.rfind(punct, 0, max_chars + 2)
            if pos > 2:
                split_idx = pos + len(punct)
                break
        return {
            "has_dialogue": True,
            "char_count": char_count,
            "cps": cps,
            "overflow": True,
            "kept": clean_text[:split_idx],
            "overflow_out": clean_text[split_idx:]
        }
    return {
        "has_dialogue": True,
        "char_count": char_count,
        "cps": cps,
        "overflow": False,
        "kept": clean_text,
        "overflow_out": None
    }


def compile_to_models(spec: dict, warn_video: bool = False) -> dict:
    """將結構化分鏡規格編譯為 Layer 1 導演卡與 Layer 3 各大模型原生 Prompt。
    影片模型的欄位先去掉 HEX（換成「色票指定」）；warn_video 為 True 時把替換次數印到 stderr。"""
    lens = LENS_OPTICS_PRESETS.get(spec["focal"], LENS_OPTICS_PRESETS["35mm"])
    view = POV_MODES.get(spec["pov"], POV_MODES["objective"])
    dlg_info = check_dialogue_pacing(spec.get("dialogue", ""), spec["duration"])
    palette_video, palette_hits = strip_hex(palette_names(spec["palette"]))  # 影片模型不收 HEX
    vspec, field_hits = {}, 0
    for key, value in spec.items():
        if isinstance(value, str) and key not in ("palette", "dialogue"):
            value, n = strip_hex(value)
            field_hits += n
        vspec[key] = value
    if warn_video and palette_hits + field_hits:
        print(f"[警告] 影片模型不收 HEX 色碼：已把 {palette_hits + field_hits} 處 #RRGGBB 替換為「色票指定」，"
              "請改用色名（例如「冷鋼夜黑」）", file=sys.stderr)

    aspect_note = (
        "9:16 豎屏縱深交錯構圖（前景虛化佔35%+中後景清晰，中近景特寫主導，關鍵手部動作抬至腰胸以上避開底部20%字幕區與右側15% UI安全區）"
        if spec["aspect"] == "9:16"
        else "16:9 橫屏寬幅三分構圖（左中右與前後景層次分明，嚴守180度水平軸線）"
    )

    # 1. Layer 1: 人類導演審閱六要素卡
    dlg_display = f"「{dlg_info['kept']}」" if dlg_info["has_dialogue"] else "（無台詞 — 強制全員閉唇鎖 lips closed）"
    if dlg_info["overflow"]:
        dlg_display += f" 【⚠️ 氣口順延警告：後半句「{dlg_info['overflow_out']}」已於氣口切斷並順延至下一鏡 J-Cut！】"

    layer1_card = (
        f"分鏡（時長 {spec['duration']}s | 畫幅 {spec['aspect']} | {lens['name']} | {view['name']}）：\n"
        f"【1. 視角與遮擋路由】：{view['desc']}（前景參照：{spec['dirty_frame_obj']}）。\n"
        f"【2. 光學與物距設定】：{lens['distance']}。{lens['spatial']}。觀眾靈魂站位：【{lens['psychology']}】。\n"
        f"【3. 畫幅幾何與空間錨點】：{aspect_note}。實體參照物錨定：{spec['anchor_obj']}。\n"
        f"【4. 動態演化與心理節奏】：主體（{spec['subject']}）➔ {spec['action']}。\n"
        f"【5. 可見微表演與尾韻物理】：{spec['expression']}。尾韻微物理：{spec['micro_tail']}。\n"
        f"【6. 鐵三角色卡與四維配音】：\n"
        f"   - 色卡空間錨定：{spec['palette']}\n"
        f"   - 對白與氣口保真：{dlg_display}\n"
        f"   - 四維發聲與音效：{spec['voice_4d']} ｜ 物理音效：{spec['sfx']}"
    )

    # 2. Layer 3 (A): 即夢 Seedance 2.0 終極自然流 (零標籤污染、一段一鏡、台詞定軌、鎖光句、尾韻微物理)
    dirty_clause = (
        f"前景由{vspec['dirty_frame_obj']}形成約30%的重度失焦遮擋（Dirty Frame），營造暗處窺視縱深；"
        if vspec["pov"] == "dirty_frame" and vspec["dirty_frame_obj"] != "無"
        else ("機位嚴格置於動作軸線正側面90度，零前景遮擋，讓碰撞接觸點100%清晰展開；" if vspec["pov"] == "clear_impact_90deg" else "")
    )
    if dlg_info["has_dialogue"]:
        mid = max(1, len(dlg_info["kept"]) // 2)
        part1, part2 = dlg_info["kept"][:mid], dlg_info["kept"][mid:]
        dlg_clause = (
            f"@{vspec['speaker']} 展現出「{vspec['expression']}」的神態，說到前半句「{part1}」時伴隨起始動作並留一口呼吸停頓，"
            f"說到後半句「{part2}」時完成核心動作並以（{vspec['voice_4d']}）的語氣清晰說道：「{dlg_info['kept']}」。"
        )
    else:
        dlg_clause = f"{vspec['subject']}展現出「{vspec['expression']}」的神態，雙唇始終保持自然閉合不發一言。"

    seedance_v8 = (
        f"{vspec['focal']}鏡頭拍攝（{lens['distance']}），{lens['spatial']}，採用{vspec['aspect']}畫幅構圖。"
        f"{dirty_clause}畫面中，{vspec['subject']}依託{vspec['anchor_obj']}確立空間位置，{vspec['action']}。"
        f"{dlg_clause}注意全場光影嚴格鎖定「{palette_video}」，不要單獨加光或改變色溫；"
        f"伴隨{vspec['sfx']}，動作結束時{vspec['micro_tail']}，全過程嚴守180度軸線，無分屏無文字。"
    )

    # 3. Layer 3 (B): MiniMax H3 官方三欄結構 (含 <d> 標記與閉唇鎖)
    if dlg_info["has_dialogue"]:
        h3_speech = f"speaks with {vspec['voice_4d']}: <d>[Chinese] {dlg_info['kept']}</d>"
    else:
        h3_speech = "while their lips remain completely closed"

    minimax_h3 = (
        f"integrated_multimodal_description:\n"
        f"Global palette and lighting locked to: {palette_video}.\n"
        f"[Shot 1] ({vspec['duration']}s, {vspec['aspect']}) {lens['distance_en']}, {lens['spatial_en']}. "
        f"Camera mode: {view['desc_en']}. Anchored by {vspec['anchor_obj']}, {vspec['subject']} performs the sequence: "
        f"{vspec['action']}. Observable expression: {vspec['expression']}, {h3_speech}. "
        f"Follow-through micro-physics: {vspec['micro_tail']}.\n\n"
        f"overall_soundscape:\n"
        f"{vspec['sfx']}.\n\n"
        f"non_diegetic_music:\n"
        f"Low atmospheric cinematic score matching the tension of the scene."
    )

    # 4. Layer 3 (C): Kling / 通用首尾幀接龍模式 (FL2VA)
    kling_fl2va = (
        f"[First-to-Last Frame Transition | {vspec['duration']}s | {vspec['aspect']}]\n"
        f"- Optical & Camera Path: {lens['distance_en']}, {view['desc_en']}.\n"
        f"- Motion Trajectory (<=5 stages): Smoothly transition from initial pose at {vspec['anchor_obj']} through ({vspec['action']}), "
        f"ending with micro-physics ({vspec['micro_tail']}).\n"
        f"- Continuity & Safety Lock: Maintain exact character identity, prop ownership, and palette ({palette_video}). "
        f"Single continuous shot, NO split screen, NO 4-panel grid, NO text."
    )

    # 5. Stage A: 漫劇 3x3 九宮格同空間鎖臉關鍵幀 Prompt
    grid_9panel = (
        f"3x3 grid cinematic storyboard sheet, 9 sequential panels (reading left-to-right, top-to-bottom), "
        f"{spec['aspect']} panel ratio, thin black borders.\n"
        f"[IDENTITY & ASSET LOCK]: {spec['subject']} at {spec['anchor_obj']}.\n"
        f"[PALETTE LOCK]: {spec['palette']}.\n"
        f"[SEQUENCE BREAKDOWN]: {spec['action']}.\n"
        f"[OPTICS]: Varying between 24mm (<0.4m extreme perspective) and 100mm (>6m telephoto compression), "
        f"incorporating {view['desc_en']}. Consistent facial features and outfit across all 9 panels, NO speech bubbles, NO text, NO watermarks."
    )

    return {
        "spec": spec,
        "dialogue_audit": dlg_info,
        "outputs": {
            "layer1-card": layer1_card,
            "seedance-v8": seedance_v8,
            "minimax-h3": minimax_h3,
            "kling-fl2va": kling_fl2va,
            "grid-9panel": grid_9panel
        }
    }


def main():
    parser = argparse.ArgumentParser(description="AI 電影與漫劇導演分鏡、光學物距與多模型編譯器 (v2.0)")
    parser.add_argument("--list-presets", action="store_true", help="列出所有內建電影級與漫劇預設配置")
    parser.add_argument("--preset", choices=list(BUILT_IN_PRESETS.keys()), help="載入內建預設場景")
    parser.add_argument("--focal", default="24mm", choices=list(LENS_OPTICS_PRESETS.keys()), help="攝影機焦段")
    parser.add_argument("--pov", default="dirty_frame", choices=list(POV_MODES.keys()), help="視角與遮擋路由模式")
    parser.add_argument("--aspect", default="16:9", choices=["16:9", "9:16"], help="畫幅比例 (16:9 橫屏 / 9:16 豎屏短劇)")
    parser.add_argument("--dirty-frame", default="半掩的門框與暗部陰影", help="前景遮擋物描述")
    parser.add_argument("--anchor", default="【紅木辦公桌】與【落地玻璃窗】", help="場景實體參照物錨點")
    parser.add_argument("--subject", default="神情冷峻的主角", help="畫面主體角色描述")
    parser.add_argument("--action", default="女主角在茶几前瘋狂翻找失落的彩票，隨後因水杯倒影而驟然僵住", help="畫面主體動作鏈")
    parser.add_argument("--expression", default="瞳孔微縮，下頜線條緊繃，眼眶微紅", help="可見五官微表演 (禁醫學解剖詞)")
    parser.add_argument("--micro-tail", default="衣角與耳畔碎髮隨呼吸氣息輕微晃動後下墜", help="動作結束尾韻微物理")
    parser.add_argument("--palette", default="冷鋼夜黑 (#0A0E17 深夜藍牆面 + #D4AF37 暖金檯燈光)",
                        help="色卡：色名＋物件＋HEX（HEX 僅出現在 Layer 1 與九宮格）")
    parser.add_argument("--speaker", default="主角", help="說話角色名稱")
    parser.add_argument("--dialogue", default="", help="劇本台詞原文 (100%%保真)")
    parser.add_argument("--voice-4d", default="壓抑低沉氣音，關鍵詞前稍作停頓，句尾下沉", help="配音演出描述（語速、停頓、氣息，用文字寫）")
    parser.add_argument("--sfx", default="細微衣料摩擦聲與沉重呼吸聲", help="物理擬音與環境音")
    parser.add_argument("--duration", type=float, default=3.5, help="鏡頭時長(秒)")
    parser.add_argument(
        "--target-model",
        default="layer1-card",
        choices=["layer1-card", "seedance-v8", "minimax-h3", "kling-fl2va", "grid-9panel", "all"],
        help="目標編譯模型格式"
    )
    parser.add_argument("--format", default="text", choices=["text", "json", "prompt", "all"], help="輸出格式 (向下相容 v1.0)")

    args = parser.parse_args()

    if args.list_presets:
        print("=" * 72)
        print("🎬 cinematic-director-storyboard v2.0 內建工業級預設庫 (Presets)")
        print("=" * 72)
        for k, v in BUILT_IN_PRESETS.items():
            print(f"  * {k:<24} : {v['title']} [焦段:{v['focal']} | 視角:{v['pov']} | 畫幅:{v['aspect']}]")
        print("=" * 72)
        return

    if args.preset:
        spec = dict(BUILT_IN_PRESETS[args.preset])
    else:
        spec = {
            "title": "自訂導演分鏡鏡頭",
            "focal": args.focal,
            "pov": args.pov,
            "aspect": args.aspect,
            "duration": args.duration,
            "dirty_frame_obj": args.dirty_frame,
            "anchor_obj": args.anchor,
            "subject": args.subject,
            "action": args.action,
            "expression": args.expression,
            "micro_tail": args.micro_tail,
            "palette": args.palette,
            "speaker": args.speaker,
            "dialogue": args.dialogue,
            "voice_4d": args.voice_4d,
            "sfx": args.sfx
        }

    warn_video = args.format == "all" or args.target_model in VIDEO_MODELS
    compiled = compile_to_models(spec, warn_video=warn_video)

    if args.format == "json":
        print(json.dumps(compiled, ensure_ascii=False, indent=2))
        return

    target = "all" if args.format == "all" else args.target_model
    if target == "all":
        print("=" * 75)
        print(f"🎬 【{spec['title']}】三層產物與多模型全編譯輸出")
        print("=" * 75)
        for name, content in compiled["outputs"].items():
            print(f"\n▶ [{name.upper()}]\n" + "-" * 75)
            print(content)
        print("=" * 75)
    else:
        if args.format == "prompt":
            print(compiled["outputs"][target])
        else:
            print("=" * 75)
            print(f"【導演分鏡光學與編譯產出】目標格式: {target} | 焦段: {spec['focal']} | 視角: {spec['pov']} | 畫幅: {spec['aspect']} | 時長: {spec['duration']}s")
            print("=" * 75)
            print(compiled["outputs"][target])
            print("=" * 75)


if __name__ == "__main__":
    main()
