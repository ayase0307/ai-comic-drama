#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ch02_data_ep03.py
第二章 EP03（果凍之災與雙姝獵妖）10 個分段資料定義
嚴格遵守《噩盡島》實戰定案：每段 8.0s，每鏡 >= 2.5s，力學三要素具體，台詞 100% 逐字吻合。
"""

def get_ep03_segments(helpers):
    ms = helpers["make_shot"]
    mseg = helpers["make_segment"]
    c = helpers["constants"]

    segments = []

    # --------------------------------------------------------------------------
    # Segment 1: EP03-S01-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s1_shots = [
        ms(
            shot_id="EP03-S01-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["果凍怪膠質體", "受困人質"],
            blocking_desc="八名受困人質隔著半透明果凍膠質窒息掙扎",
            action_stages=[
                "八名受困旅客隔著藍白透明膠質肉壁面孔極度扭曲",
                "口鼻被黏稠液體封死無聲張大呼救手臂漸漸癱軟",
                "果凍肌體在體表蠕動將人質向體內更深處吞噬陷沒"
            ],
            observable_expression="窒息瀕死的極致痛苦與無助",
            has_dialogue=False,
            foley="黏液翻湧滑膩咕嘟聲與悶在體內的微弱嗚咽",
            h3_action_en="eight trapped victims struggle inside the translucent blue-white jelly monster under ceiling lamps then their arms slowly grow limp as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S01-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="trucks left",
            axis_side="right",
            anchor_objects=["沈洛年", "紅色消火栓箱", "沉重消防斧"],
            blocking_desc="沈洛年狂奔拉開消火栓箱，拽出沉重消防斧",
            action_stages=[
                "沈洛年咬牙大步狂奔衝至大廳牆邊紅色消防栓櫃前",
                "一把暴力扯開鐵門從金屬支架上拽下一柄沉重的紅柄消防斧",
                "雙手緊握斧柄回身向果凍巨物全速衝刺"
            ],
            observable_expression="決絕果斷，奮不顧身之勇氣",
            has_dialogue=False,
            foley="消防箱鐵門被暴力拉開匡啷巨響與重斧出架聲",
            h3_action_en="<Subject 1> sprints across the granite floor under the station light and yanks open the red hydrant cabinet then pulls out a heavy fire axe as the camera trucks left",
            h3_camera_en="trucks left"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S01",
        segment_id="EP03-S01-seg01",
        source_scene_id="EP03-S01",
        lighting_lock=c["LIGHTING_S04_STATION_AXE"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SHEN"]],
        shots=s1_shots,
        end_state_desc="人質在果凍內窒息，沈洛年自消防箱拔出大斧衝出",
        h3_summary_en="Trapped civilians suffocate inside the giant slime, prompting Shen Luonian to retrieve a heavy fire axe from a wall cabinet.",
        h3_soundscape_en="Wet gelatinous suction noises, metal door clattering, heavy breathing in vast transit hall.",
        h3_music_en="Urgent thumping battle drums and high-tension strings."
    ))

    # --------------------------------------------------------------------------
    # Segment 2: EP03-S01-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s2_shots = [
        ms(
            shot_id="EP03-S01-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.0m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "消防斧", "果凍怪切口"],
            blocking_desc="沈洛年狂劈果凍怪，斧刃切入切口瞬間黏攏閉合",
            action_stages=[
                "沈洛年雙手高舉消防斧全身重量狂暴下劈在果凍軀幹上",
                "鋒利鋼斧深深斬入半米膠質肌肉激起一圈黏稠水波漣漪",
                "斧刃剛抽出切口肉質便如活物般瞬間閉合黏攏完好如初"
            ],
            observable_expression="咬牙全力發力，隨後轉為震撼錯愕",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="皮這麼厚，砍不開？",
            voice_4d_spec="ShenLuonian_StrainingSlash_v1",
            foley="沉重斧刃劈入膠質水聲、水波翻騰聲與皮肉黏合聲",
            h3_action_en="<Subject 1> hacks the steel axe into the thick jelly monster under commercial lights but the wound instantly seals together as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S01-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "震麻的手掌"],
            blocking_desc="沈洛年握斧後退氣喘吁吁深感無力",
            action_stages=[
                "沈洛年握著消防斧連退兩步胸膛劇烈起伏喘粗氣",
                "虎口被果凍肉體彈力震得隱隱發麻酸痛",
                "死死瞪著毫髮無損的果凍巨怪心中升起深深無力感"
            ],
            observable_expression="氣喘吁吁，心焦憤慨卻無從下手",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="這黏糊糊的到底是什麼！",
            voice_4d_spec="ShenLuonian_FrustratedGasp_v1",
            foley="沉重粗重喘息聲與金屬斧柄緊握皮革摩擦聲",
            h3_action_en="<Subject 1> stumbles backward panting heavily with his axe under the lamps then stares in deep frustration at the invulnerable slime as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S01",
        segment_id="EP03-S01-seg02",
        source_scene_id="EP03-S01",
        lighting_lock=c["LIGHTING_S04_STATION_AXE"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SHEN"]],
        shots=s2_shots,
        end_state_desc="斧劈果凍瞬息閉合無效，沈洛年退後氣喘震驚",
        h3_summary_en="Shen Luonian's axe chops harmlessly reseal inside the jelly monster, leaving him panting in helpless bewilderment.",
        h3_soundscape_en="Squishy wet resealing sounds, panting breath, eerie distant station alarms.",
        h3_music_en="Despairing brass chords descending into tense silence."
    ))

    # --------------------------------------------------------------------------
    # Segment 3: EP03-S02-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s3_shots = [
        ms(
            shot_id="EP03-S02-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="4.0m distance",
            pov_routing="objective",
            movement="pans right",
            axis_side="left",
            anchor_objects=["車站側門", "雙姝身影", "夜風破門"],
            blocking_desc="側門狂風呼嘯，雙姝如雷霆掠入大廳",
            action_stages=[
                "車站側門狂風驟起兩道矯健身影如疾電般破風殺入大廳",
                "褐髮女子身背厚重雕花大刀步履如飛身形迅猛",
                "黑髮風衣女子身姿輕盈手按腰間緊隨其後掠過人群"
            ],
            observable_expression="強者破門而入之凌厲與自信",
            has_dialogue=False,
            foley="狂風破門呼嘯聲、疾速奔跑破空聲與風衣獵獵作響",
            h3_action_en="the station side doors blast open in cool night light as two athletic warrior women dash inside with lightning agility as the camera pans right",
            h3_camera_en="pans right"
        ),
        ms(
            shot_id="EP03-S02-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="tilts up",
            axis_side="center",
            anchor_objects=["褐髮持刀女", "青色雕花厚背刀"],
            blocking_desc="褐髮女縱身躍起數米凌空拔刀狂笑斷喝",
            action_stages=[
                "褐髮女雙腳踏地縱身凌空躍起數米高高凌駕眾人頭頂",
                "雙手拔出青色雕花厚背大刀迎風狂笑揮灑豪邁",
                "刀氣激起青色旋風向下方人群發出雷霆斷喝驅散"
            ],
            observable_expression="豪邁縱笑，睥睨全場之戰意",
            has_dialogue=True,
            speaker="brown-hair-slayer",
            line_verbatim="一群笨蛋在幹嘛？都讓開！",
            voice_4d_spec="BrownHairSlayer_HeroicLaugh_v1",
            foley="踏地爆裂聲、厚刀出鞘龍吟鏗鏘聲與豪氣清亮大喝",
            h3_action_en="<Subject 1> leaps several meters high in the station lighting while unsheathing her heavy cyan steel broadsword then roars with laughter as the camera tilts up",
            h3_camera_en="tilts up"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S02",
        segment_id="EP03-S02-seg01",
        source_scene_id="EP03-S02",
        lighting_lock=c["LIGHTING_S04_STATION_DUO"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SLAYER"]],
        shots=s3_shots,
        end_state_desc="雙姝破門殺入，褐髮女凌空拔刀發出豪邁大喝",
        h3_summary_en="The two demon slayer women burst into the hall and the brown-haired warrior leaps into the air with her massive broadsword.",
        h3_soundscape_en="Rushing gale wind, metallic sword unsheathing ringing, vibrant battle cry.",
        h3_music_en="Heroic driving electric rock-orchestral riff erupting."
    ))

    # --------------------------------------------------------------------------
    # Segment 4: EP03-S02-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s4_shots = [
        ms(
            shot_id="EP03-S02-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="right",
            anchor_objects=["青色大刀刀芒", "果凍肉屑"],
            blocking_desc="厚背刀青芒連閃，如切凝脂削去外層果凍",
            action_stages=[
                "褐髮女自半空如流星下墜雙臂青筋凸起青色厚背刀怒斬",
                "刀身青芒暴漲連環化作十餘道銳利殘影快刀削肉",
                "如切凝脂般將外層果凍膠質削成漫天碎片飛落"
            ],
            observable_expression="戰意昂揚，豪邁痛快",
            has_dialogue=True,
            speaker="brown-hair-slayer",
            line_verbatim="哈！吃姑奶奶一刀！",
            voice_4d_spec="BrownHairSlayer_FierceStrike_v1",
            foley="厚刀撕裂空氣刺耳厲嘯、膠質橫飛爆裂聲與暢快清嘯",
            h3_action_en="<Subject 1> descends like a thunderbolt under cyan sparks slicing the jelly monster repeatedly with radiant blade arcs as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S02-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="trucks left",
            axis_side="left",
            anchor_objects=["受困警員", "褐髮持刀女手掌"],
            blocking_desc="褐髮女左手探入扯出受困警員與人質甩向安全地帶",
            action_stages=[
                "厚背刀精準挑開深層肉膜形成空隙",
                "褐髮女左手閃電般探入黏液一把揪住受困警員衣領",
                "運勁一甩將人質安全拋飛至後方空曠地磚滑行脫險"
            ],
            observable_expression="救人俐落從容，身手矯健",
            has_dialogue=False,
            foley="黏液拉絲撕開黏稠聲與人質安全滑落地磚摩擦聲",
            h3_action_en="she reaches her left hand through the severed membrane in ambient light then hurls the gasping victims safely onto the open granite floor as the camera trucks left",
            h3_camera_en="trucks left"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S02",
        segment_id="EP03-S02-seg02",
        source_scene_id="EP03-S02",
        lighting_lock=c["LIGHTING_S04_STATION_DUO"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SLAYER"]],
        shots=s4_shots,
        end_state_desc="褐髮女快刀削去果凍救出人質，展現強大刀法",
        h3_summary_en="The brown-haired warrior slashes open the slime monster with brilliant cyan blade arcs, safely hauling the trapped hostages out.",
        h3_soundscape_en="Blade swooshes slicing through jelly, wet splatter, grateful gasps of rescued people.",
        h3_music_en="Triumphant electric guitar melodies surging with battle momentum."
    ))

    # --------------------------------------------------------------------------
    # Segment 5: EP03-S02-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s5_shots = [
        ms(
            shot_id="EP03-S02-SH05",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.5m distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="left",
            anchor_objects=["黑髮道術女", "霧面銀窄匕首"],
            blocking_desc="黑髮女抽匕首上前冷聲提醒妖氣分散無核",
            action_stages=[
                "黑髮女子從深灰風衣口袋中抽出細窄霧面銀色匕首",
                "步履沉穩上前目光如電穿透果凍巨怪體表窺視本質",
                "語調冰冷沉著提醒同伴停止無效砍殺"
            ],
            observable_expression="目光深邃冷靜，洞察秋毫之從容",
            has_dialogue=True,
            speaker="black-hair-daoist",
            line_verbatim="別鬧了，這妖物的妖氣是散的。",
            voice_4d_spec="BlackHairDaoist_CoolStern_v1",
            foley="銀匕首出鞘細微金屬磨損聲與冷冽女性發音",
            h3_action_en="<Subject 1> unsheathes a narrow silver dagger under station lighting and steps forward then speaks in a cool commanding voice as the camera dollies in",
            h3_camera_en="dollies in"
        ),
        ms(
            shot_id="EP03-S02-SH06",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="objective",
            movement="static",
            axis_side="right",
            anchor_objects=["褐髮持刀女", "拄地厚背大刀"],
            blocking_desc="褐髮女收刀拄地歪頭發愁如何打擊",
            action_stages=[
                "褐髮女反手將厚背大刀重重拄在地面濺起細碎火星",
                "單手叉腰歪著腦袋注視著散落蠕動的肉塊發愁",
                "嘴角微揚露出一絲意猶未盡的苦笑"
            ],
            observable_expression="無奈苦笑，眼神中仍有躍躍欲試之興奮",
            has_dialogue=True,
            speaker="brown-hair-slayer",
            line_verbatim="難怪找不到核，這要怎麼打？",
            voice_4d_spec="BrownHairSlayer_PuzzledLaugh_v1",
            foley="沉重大刀金屬尖端頓地鏗鏘聲與微弱笑聲",
            h3_action_en="the warrior woman plants the tip of her broadsword against the granite floor in cold light then sighs with a playful grin as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S02",
        segment_id="EP03-S02-seg03",
        source_scene_id="EP03-S02",
        lighting_lock=c["LIGHTING_S04_STATION_DUO"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_DAOIST"]],
        shots=s5_shots,
        end_state_desc="黑髮女點破妖氣散溢，褐髮女拄刀商議戰術",
        h3_summary_en="The daoist woman observes that the monster's spiritual energy is dispersed, prompting her partner to ponder their attack strategy.",
        h3_soundscape_en="Blade planted on stone floor, subtle hum of mystical qi energy, quiet hall.",
        h3_music_en="Mysterious mystical synthesized arpeggios and rhythmic percussion."
    ))

    # --------------------------------------------------------------------------
    # Segment 6: EP03-S03-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s6_shots = [
        ms(
            shot_id="EP03-S03-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="static",
            axis_side="center",
            anchor_objects=["融合成團的果凍怪球", "翻騰藍白黏液"],
            blocking_desc="果凍碎塊互相吸引，飛速融合成兩公尺高巨型怪球",
            action_stages=[
                "散落在大理石地面上的無數果凍肉塊如磁石般相互吸引滑動",
                "迅速聚集融合為一顆高達兩米表面不斷翻滾起泡的藍白怪球",
                "妖氣在怪球內翻江倒海散發出陣陣刺鼻酸臭氣體"
            ],
            observable_expression="妖體聚合時的詭異蠕動與惡臭翻滾",
            has_dialogue=False,
            foley="無數黏液匯聚滑動咕嘰聲與內部氣泡破裂噗噗聲",
            h3_action_en="the scattered severed jelly fragments slide together like magnets under station lighting then merge into a two-meter blue-white sphere as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S03-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["黑髮道術女", "反握銀匕首", "虛空劍指"],
            blocking_desc="黑髮女劍指下壓叱出重力法訣",
            action_stages=[
                "黑髮女右手反握霧面銀匕首凝神調動體內渾厚真氣",
                "左手劍指凌空朝兩米巨型怪球正上方虛空重重一壓",
                "薄唇微啟吐氣如雷叱出一聲震懾神魂的號令"
            ],
            observable_expression="雙目精芒奪目，威嚴冷峻如天神",
            has_dialogue=True,
            speaker="black-hair-daoist",
            line_verbatim="聚好了。落！",
            voice_4d_spec="BlackHairDaoist_SternIncantation_v1",
            foley="道術真氣激盪嗡鳴與清冷斷喝聲",
            h3_action_en="<Subject 1> points her slender fingers downward with arcane qi focus in ambient light then commands firmly as gravity warps the air as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S03",
        segment_id="EP03-S03-seg01",
        source_scene_id="EP03-S03",
        lighting_lock=c["LIGHTING_S04_STATION_GRAVITY"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_DAOIST"]],
        shots=s6_shots,
        end_state_desc="果凍融合成兩米巨球，黑髮女指空叱令引動重力",
        h3_summary_en="The severed jelly fragments combine into a massive sphere, and the daoist woman exerts an immense gravitational field over it.",
        h3_soundscape_en="Bubbling slime suction, intense low hum of spatial compression, clear solemn vocal command.",
        h3_music_en="Ominous sub-bass vibration shaking the sonic foundation."
    ))

    # --------------------------------------------------------------------------
    # Segment 7: EP03-S03-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s7_shots = [
        ms(
            shot_id="EP03-S03-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="center",
            anchor_objects=["被壓扁的果凍怪", "噴濺的酸臭汁液", "排水孔"],
            blocking_desc="萬鈞無形重力壓扁怪球，大量酸液瘋狂噴濺入排水溝",
            action_stages=[
                "虛空中彷彿有萬鈞無形巍峨重山轟然垂直墜落砸在怪球上方",
                "龐大果凍怪身被極致重力硬生生壓迫碾扁成不足十公分的薄片",
                "體內大量酸臭墨綠汁液如噴泉般自邊緣瘋狂噴射衝入排水溝孔"
            ],
            observable_expression="不可抗拒之重力摧殘碾壓",
            has_dialogue=False,
            foley="萬鈞空氣重壓轟鳴震爆、液體如高壓水槍狂噴入溝聲",
            h3_action_en="invisible crushing gravity flattens the giant jelly sphere onto the floor tiles under purple ambient glow then forces litres of acidic fluid into the open storm drain as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S03-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.5m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["黑髮道術女", "翻轉銀匕首"],
            blocking_desc="黑髮女匕首反轉散開法訣提醒妖氣聚攏",
            action_stages=[
                "黑髮女右手銀匕首在掌心瀟灑反轉向上收回指尖",
                "壓迫虛空的無形重力場在短叱聲中驟然撤除消散",
                "冷靜指出妖核已經被強行脫水擠壓暴露在乾球中心"
            ],
            observable_expression="神情淡定自若，運籌帷幄盡在掌握",
            has_dialogue=True,
            speaker="black-hair-daoist",
            line_verbatim="散！妖氣聚在一起了。",
            voice_4d_spec="BlackHairDaoist_CalmRelease_v1",
            foley="匕首在指間翻轉破空微鳴與重力驟消氣浪呼嘯",
            h3_action_en="<Subject 1> flips her silver dagger deftly in the station lighting then commands the gravity field to release as demonic energy condenses into the core as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S03",
        segment_id="EP03-S03-seg02",
        source_scene_id="EP03-S03",
        lighting_lock=c["LIGHTING_S04_STATION_GRAVITY"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_DAOIST"]],
        shots=s7_shots,
        end_state_desc="重力榨乾果凍排出酸水，黑髮女散法露出緊縮妖核",
        h3_summary_en="The massive gravity pressure crushes the jelly flat and purges its fluids, condensing its core as the daoist releases the spell.",
        h3_soundscape_en="Deafening gravity hum, rushing sewer drain flow, crisp knife flip sound.",
        h3_music_en="Sudden dramatic pause and rising high-voltage battle anticipation."
    ))

    # --------------------------------------------------------------------------
    # Segment 8: EP03-S03-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s8_shots = [
        ms(
            shot_id="EP03-S03-SH05",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="clear_impact_90deg",
            movement="trucks right",
            axis_side="left",
            anchor_objects=["褐髮持刀女", "青色雷光大刀", "乾癟怪球"],
            blocking_desc="褐髮女雙目精芒大盛踏步暴射而出",
            action_stages=[
                "褐髮女眼中璀璨精芒大盛雙腳在地面踏碎瓷磚暴射而出",
                "重力驟消後嚴重脫水的果凍怪急劇縮成半米乾癟皺褶怪球",
                "厚背大刀揚至腦後蓄力如滿月雷霆在刀脊瘋狂跳躍"
            ],
            observable_expression="戰意狂暴昂揚，狂笑中帶著獵手嗜血",
            has_dialogue=True,
            speaker="brown-hair-slayer",
            line_verbatim="輪到我了！",
            voice_4d_spec="BrownHairSlayer_FierceRoar_v1",
            foley="踏碎瓷磚雷霆爆響、電弧跳躍滋滋聲與興奮戰吼",
            h3_action_en="<Subject 1> charges forward under cyan lighting with intense lightning aura crackling along her heavy broadsword then roars with fierce delight as the camera trucks right",
            h3_camera_en="trucks right"
        ),
        ms(
            shot_id="EP03-S03-SH06",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="center",
            anchor_objects=["青色雷霆刀氣", "一刀兩斷的怪球"],
            blocking_desc="雷鳴一刀兩斷，怪球自中央被精準平整斬開",
            action_stages=[
                "青色雕花厚背刀在霹靂雷鳴狂暴聲浪中自天頂垂直力劈而下",
                "耀眼青色雷電刀芒以摧枯拉朽之勢斬裂空氣貫穿乾癟怪球",
                "怪球自中央被精準平整一刀兩斷向兩側轟然裂開倒下"
            ],
            observable_expression="雷霆萬鈞之斬殺終結",
            has_dialogue=False,
            foley="雷霆霹靂破空炸響、刀鋒入地金石轟鳴與焦臭白煙升起",
            h3_action_en="the cyan steel broadsword crashes downward with a thunderous roar through ambient lights then slices the dried monster cleanly in two halves as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S03",
        segment_id="EP03-S03-seg03",
        source_scene_id="EP03-S03",
        lighting_lock=c["LIGHTING_S04_STATION_GRAVITY"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SLAYER"]],
        shots=s8_shots,
        end_state_desc="褐髮女雷霆大刀一擊必殺，怪球被斬成兩段倒地",
        h3_summary_en="The brown-haired warrior unleashes a thunderous broadsword strike, cleaving the dried monster neatly in half.",
        h3_soundscape_en="Thunderous electrical explosion, concrete cracking, smoke hiss.",
        h3_music_en="Explosive climax of electric guitar and triumphant orchestral fanfare."
    ))

    # --------------------------------------------------------------------------
    # Segment 9: EP03-S04-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s9_shots = [
        ms(
            shot_id="EP03-S04-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["焦黑碎渣", "收刀回鞘"],
            blocking_desc="劈開怪球化為焦黑碎渣，褐髮女收刀入鞘",
            action_stages=[
                "被劈開的怪球斷面滋滋冒出白煙迅速碳化乾癟枯萎",
                "短短兩秒內徹底化為兩灘毫無生機妖氣盡散的焦黑碎渣",
                "褐髮女熟練甩動手腕將厚背大刀插回背後黑皮鞘套喀噠鎖定"
            ],
            observable_expression="戰事平息，氣定神閒從容自若",
            has_dialogue=False,
            foley="碳化焦黑滋滋聲、大刀入鞘清脆鎖定喀噠聲",
            h3_action_en="the severed halves disintegrate rapidly into burnt black ashes on the station floor under restored lamps then the warrior woman slides her broadsword smoothly into its scabbard as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP03-S04-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="pans left",
            axis_side="center",
            anchor_objects=["褐髮持刀女", "歡呼群眾"],
            blocking_desc="周圍群眾歡呼，褐髮女笑瞇瞇揮手收工",
            action_stages=[
                "周圍躲避在柱後的圍觀群眾爆發出雷鳴般的驚呼與喝采",
                "褐髮女笑瞇瞇地轉過身輕鬆地朝四方眾人揮了揮手",
                "邁著豪邁步伐招呼黑髮同伴準備撤離現場"
            ],
            observable_expression="大大咧咧笑瞇瞇，神態自若灑脫",
            has_dialogue=True,
            speaker="brown-hair-slayer",
            line_verbatim="沒事了沒事了，大家收工！",
            voice_4d_spec="BrownHairSlayer_CheerfulWrapUp_v1",
            foley="大廳群眾雷鳴歡呼鼓掌聲與豪邁大笑招呼聲",
            h3_action_en="<Subject 1> turns to the cheering onlookers in the warm station lighting and waves her hand cheerfully then strides toward the exit as the camera pans left",
            h3_camera_en="pans left"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S04",
        segment_id="EP03-S04-seg01",
        source_scene_id="EP03-S04",
        lighting_lock=c["LIGHTING_S04_STATION_RESOLVE"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SLAYER"]],
        shots=s9_shots,
        end_state_desc="怪球化為焦黑碎渣，褐髮女收刀向歡呼群眾揮手致意",
        h3_summary_en="The demon dissolves into black ash, and the cheerful warrior woman waves to the cheering crowd as she sheathes her blade.",
        h3_soundscape_en="Resonant station cheers, clapping crowd, light cheerful feminine voice.",
        h3_music_en="Upbeat victory fanfare transitioning into playful groove."
    ))

    # --------------------------------------------------------------------------
    # Segment 10: EP03-S04-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s10_shots = [
        ms(
            shot_id="EP03-S04-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.2m distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="left",
            anchor_objects=["沈洛年", "捲刃消防斧", "立柱陰影"],
            blocking_desc="沈洛年握著消防斧退到立柱陰影大口喘息",
            action_stages=[
                "沈洛年渾身被冷汗與雨水浸透握著消防斧退入大理石立柱陰影",
                "背靠冰涼石柱胸膛如拉風箱般劇烈起伏大口喘息",
                "低頭凝視著手中微微捲刃的斧柄虎口滲出微弱血痕"
            ],
            observable_expression="心有餘悸，大戰後的體力透支與迷茫",
            has_dialogue=False,
            foley="急促粗重呼吸聲、冷汗滑落聲與沉重靠柱悶響",
            h3_action_en="<Subject 1> retreats into the pillar shadows under warm ceiling lights gripping his notched fire axe then breathes heavily in total exhaustion as the camera dollies in",
            h3_camera_en="dollies in"
        ),
        ms(
            shot_id="EP03-S04-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年漆黑雙眸", "焦黑妖怪碎渣"],
            blocking_desc="沈洛年低頭看斷斧心悸低語世界瘋了",
            action_stages=[
                "沈洛年緩緩抬起漆黑眼眸凝望地上冒煙的黑色妖怪殘渣",
                "喉頭微動低聲自嘲般喃喃自語心緒翻江倒海",
                "眼神中浮現出對未來生活徹底失控的迷茫與警惕"
            ],
            observable_expression="自嘲心悸，迷茫而警惕的複雜眼神",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="一天遇到三次……世界瘋了。",
            voice_4d_spec="ShenLuonian_WearyWhisper_v1",
            foley="低沉疲憊自嘲喃喃聲與車站廣播遠處背景聲",
            h3_action_en="<Subject 1> stares down at the steaming black residue in the restored lighting then mutters wryly under his breath in deep bewilderment as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP03-S04",
        segment_id="EP03-S04-seg02",
        source_scene_id="EP03-S04",
        lighting_lock=c["LIGHTING_S04_STATION_RESOLVE"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SHEN"]],
        shots=s10_shots,
        end_state_desc="沈洛年隱於立柱陰影，握斧心悸感嘆世界瘋狂（全章總結尾）",
        h3_summary_en="Hidden in the shadow of a pillar, Shen Luonian stares at his damaged axe and whispers in disbelief at how crazy the world has become.",
        h3_soundscape_en="Echo of distant station announcements, quiet ragged breathing, lonely atmosphere.",
        h3_music_en="Haunting introspective piano and low strings fading into silence."
    ))

    return segments
