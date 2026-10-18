#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ch02_data_ep01.py
第二章 EP01（巷道殘局與拒絕邀請）10 個分段資料定義
嚴格遵守《噩盡島》實戰定案：每段 8.0s，每鏡 >= 2.5s，力學三要素具體，台詞 100% 逐字吻合。
"""

def get_ep01_segments(helpers):
    ms = helpers["make_shot"]
    mseg = helpers["make_segment"]
    c = helpers["constants"]

    segments = []

    # --------------------------------------------------------------------------
    # Segment 1: EP01-S01-seg01 (8.0s, 3 shots: 2.8s + 2.7s + 2.5s)
    # --------------------------------------------------------------------------
    s1_shots = [
        ms(
            shot_id="EP01-S01-SH01",
            start_time=0.0,
            duration=2.8,
            dramatic_beat_type="Combat_Impact",
            shot_size="ELS",
            focal_length="24mm",
            physical_distance=">6m telephoto compression",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="left",
            anchor_objects=["水泥青苔牆", "黃色巨蟒殘軀"],
            blocking_desc="巨蟒在青苔巷道中央劇烈翻滾抽搐收縮",
            action_stages=[
                "黃色巨蟒腰腹肌肉劇烈痙攣抽搐",
                "妖氣自金色鱗片縫隙大量潰散化為淡淡黃煙",
                "龐大蟒軀急劇脫水坍塌收縮為拇指粗細之黃色細蟲癱在地面"
            ],
            observable_expression="巨獸散功後的極致萎縮與無力癱軟",
            has_dialogue=False,
            foley="妖氣潰散嘶嘶聲與肉體萎縮骨骼脆響",
            h3_action_en="the monstrous yellow python violently convulses on the pavement then as its demonic aura disperses in smoke it rapidly shrinks down into a thumb-sized yellow caterpillar",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S01-SH02",
            start_time=2.8,
            duration=2.7,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m eye-level distance",
            pov_routing="objective",
            movement="pans right",
            axis_side="left",
            anchor_objects=["葉瑋珊", "絲質手絹", "黃色細蟲"],
            blocking_desc="葉瑋珊上前俯身以手絹懸空裹蟲",
            action_stages=[
                "右手探入制服口袋抽出潔白真絲手絹",
                "手腕平穩前探懸空下垂以絲絹包裹地面細蟲",
                "指尖收攏將細蟲包裹嚴實提離地面"
            ],
            observable_expression="神情冷靜專注，眉宇間帶著一絲嚴謹",
            has_dialogue=False,
            foley="絲綢摩擦沙沙聲與細蟲輕微蠕動聲",
            h3_action_en="<Subject 1> draws a clean white silk handkerchief from her uniform pocket then gently wraps the tiny insect from above as the camera pans right",
            h3_camera_en="pans right"
        ),
        ms(
            shot_id="EP01-S01-SH03",
            start_time=5.5,
            duration=2.5,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["葉瑋珊", "絲質手絹包裹"],
            blocking_desc="葉瑋珊蹙眉遞出手絹",
            action_stages=[
                "葉瑋珊微蹙眉頭將包裹的絲絹向前平穩遞出",
                "目光直視對方手部動作提醒防護",
                "手臂停留在半空中保持平穩交付姿態"
            ],
            observable_expression="眉宇微蹙，眼神嚴肅認真",
            has_dialogue=True,
            speaker="ye-weishan",
            line_verbatim="別用手抓，拿好。",
            voice_4d_spec="YeWeishan_SeriousCompose_v1",
            foley="衣料微弱摩挲與遠處校園鐘聲殘響",
            h3_action_en="<Subject 1> slightly furrows her delicate brows and extends the wrapped handkerchief forward then holds her posture firmly as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S01",
        segment_id="EP01-S01-seg01",
        source_scene_id="EP01-S01",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_YE"]],
        shots=s1_shots,
        end_state_desc="黃色巨蟒萎縮成細蟲，葉瑋珊以手絹包裹遞出",
        h3_summary_en="The defeated yellow serpent shrinks into a tiny caterpillar and Ye Weishan carefully wraps it in a silk handkerchief to hand it over.",
        h3_soundscape_en="Low hum of sunset breeze through the concrete alley with distant birds chirping, followed by soft silk rustling.",
        h3_music_en="Tense eerie strings gradually resolving into a calm mysterious melody."
    ))

    # --------------------------------------------------------------------------
    # Segment 2: EP01-S01-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s2_shots = [
        ms(
            shot_id="EP01-S01-SH04",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="50mm",
            physical_distance="1.5m eye-level distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="right",
            anchor_objects=["賴一心", "絲絹包裹"],
            blocking_desc="賴一心咧嘴接過手絹包裹",
            action_stages=[
                "賴一心爽朗咧嘴接過絲絹包裹",
                "低頭凝視手絹中微微蠕動的細蟲",
                "嘴角泛起明朗好奇的微笑"
            ],
            observable_expression="咧嘴爽朗微笑，目光明亮好奇",
            has_dialogue=True,
            speaker="lai-yixin",
            line_verbatim="這妖怪縮得真快。",
            voice_4d_spec="LaiYixin_CheerfulBoyish_v1",
            foley="接過手絹沙沙聲與爽朗輕笑",
            h3_action_en="<Subject 1> grins broadly as he receives the wrapped silk handkerchief then gazes down at the wriggling caterpillar as the camera dollies in",
            h3_camera_en="dollies in"
        ),
        ms(
            shot_id="EP01-S01-SH05",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.2m distance",
            pov_routing="objective",
            movement="static",
            axis_side="right",
            anchor_objects=["賴一心", "銀槍三節棍", "白皮長背包"],
            blocking_desc="賴一心收銀槍為三節短棍插回長背包",
            action_stages=[
                "右手手腕輕巧向內抖動卸力",
                "修長銀槍關節喀嚓清脆咬合折疊成三節短棍",
                "順勢反手將折疊三節棍穩固插入身後白皮長背包槽位"
            ],
            observable_expression="動作嫻熟流暢，神色自信從容",
            has_dialogue=False,
            foley="銀槍金屬關節連續喀嚓咬合聲與入袋滑動聲",
            h3_action_en="<Subject 1> deftly flicks his right wrist then the sleek silver spear cleanly snaps and folds into a three-section staff as he slots it behind his back into the white leather bag as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S01",
        segment_id="EP01-S01-seg02",
        source_scene_id="EP01-S01",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_LAI"]],
        shots=s2_shots,
        end_state_desc="賴一心接過手絹並將銀槍折疊收納入後背包",
        h3_summary_en="Lai Yixin cheerfully accepts the insect packet and collapses his silver spear into a three-section staff into his backpack.",
        h3_soundscape_en="Crisp metallic clicks of the folding spear echoing between narrow concrete walls.",
        h3_music_en="Light energetic acoustic strings highlighting youthful confidence."
    ))

    # --------------------------------------------------------------------------
    # Segment 3: EP01-S01-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s3_shots = [
        ms(
            shot_id="EP01-S01-SH06",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="pans left",
            axis_side="right",
            anchor_objects=["賴一心", "黃宗儒", "青苔水泥牆"],
            blocking_desc="賴一心扶起跌坐在地瑟瑟發抖的黃宗儒",
            action_stages=[
                "賴一心大步邁前彎下腰身",
                "雙手有力托住黃宗儒雙臂將其自冰冷水泥地面扶起",
                "拍打黃宗儒背部幫助其緩解恐慌站穩"
            ],
            observable_expression="神情熱切關懷，眼中滿是鼓舞",
            has_dialogue=False,
            foley="腳步踏在水泥碎石聲與衣物摩挲聲",
            h3_action_en="<Subject 1> steps forward and bends down then firmly helps the trembling boy off the dusty alley ground onto his feet as the camera pans left",
            h3_camera_en="pans left"
        ),
        ms(
            shot_id="EP01-S01-SH07",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="50mm",
            physical_distance="1.8m eye-level distance",
            pov_routing="objective",
            movement="static",
            axis_side="right",
            anchor_objects=["賴一心"],
            blocking_desc="賴一心興奮環顧眾人贊同膽量",
            action_stages=[
                "賴一心熱血地環顧四周在場眾人",
                "揚起下巴露出由衷佩服與興奮的笑容",
                "右手握拳輕輕一振彰顯少年意氣"
            ],
            observable_expression="興奮熱忱，雙目炯炯有神",
            has_dialogue=True,
            speaker="lai-yixin",
            line_verbatim="你們膽子真大，敢衝上去打！",
            voice_4d_spec="LaiYixin_Enthusiastic_v1",
            foley="風掠過制服衣角聲與熱烈語氣微喘",
            h3_action_en="<Subject 1> raises his chin enthusiastically looking around then pumps his right fist lightly as a confident smile brightens his face as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S01",
        segment_id="EP01-S01-seg03",
        source_scene_id="EP01-S01",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_LAI"]],
        shots=s3_shots,
        end_state_desc="黃宗儒被扶起站定，賴一心讚揚眾人敢於對抗妖怪",
        h3_summary_en="Lai Yixin helps Huang Zongru up and praises everyone warmly for their courage in confronting the monster.",
        h3_soundscape_en="Gentle evening breeze rustling leaves over the wall with quiet alley ambiance.",
        h3_music_en="Warm spirited melody rising with hopeful brass accents."
    ))

    # --------------------------------------------------------------------------
    # Segment 4: EP01-S01-seg04 (8.0s, 2 shots: 4.5s + 3.5s)
    # --------------------------------------------------------------------------
    s4_shots = [
        ms(
            shot_id="EP01-S01-SH08",
            start_time=0.0,
            duration=4.5,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m eye-level distance",
            pov_routing="objective",
            movement="trucks left",
            axis_side="right",
            anchor_objects=["賴一心"],
            blocking_desc="賴一心向眾人發出組隊捉妖邀請",
            action_stages=[
                "賴一心向前邁出半步神情誠摯而莊重",
                "張開手掌做出共同奮鬥的邀請姿態",
                "眼神清澈熾熱充滿對守護正義的信念"
            ],
            observable_expression="神情真誠篤定，帶著熱血少年的無畏",
            has_dialogue=True,
            speaker="lai-yixin",
            line_verbatim="世界出危機了，要不要一起抓妖？",
            voice_4d_spec="LaiYixin_HeroicInvite_v1",
            foley="踏步沉穩聲與夕陽微風拂過耳際",
            h3_action_en="<Subject 1> takes half a step forward in warm sunlight then extends his open palm in an earnest gesture of camaraderie as the camera trucks left",
            h3_camera_en="trucks left"
        ),
        ms(
            shot_id="EP01-S01-SH09",
            start_time=4.5,
            duration=3.5,
            dramatic_beat_type="Dramatic_Core",
            shot_size="CU",
            focal_length="85mm",
            physical_distance="1.0m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["黃宗儒", "厚黑框眼鏡"],
            blocking_desc="黃宗儒滿頭冷汗結巴答應加入",
            action_stages=[
                "黃宗儒額角大顆冷汗滾落滑過厚黑框眼鏡",
                "雙手緊張地緊緊攥住肥大校服衣角劇烈顫抖",
                "結巴著猛烈點頭答應表態"
            ],
            observable_expression="滿頭冷汗，眼神雖驚恐但透出堅定",
            has_dialogue=True,
            speaker="huang-zongru",
            line_verbatim="我……我相信！我加入！",
            voice_4d_spec="HuangZongru_StutterNervous_v1",
            foley="粗重緊張呼吸聲與衣角揉搓窸窣聲",
            h3_action_en="<Subject 1> sweats profusely under his thick glasses then stutters nervously while nodding vigorously in agreement as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S01",
        segment_id="EP01-S01-seg04",
        source_scene_id="EP01-S01",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_HUANG"]],
        shots=s4_shots,
        end_state_desc="賴一心發出抓妖邀請，黃宗儒激動結巴答應加入隊伍",
        h3_summary_en="Lai Yixin invites everyone to team up and hunt monsters, and the nervous Huang Zongru eagerly joins.",
        h3_soundscape_en="Soft ambient evening sounds with nervous heavy breathing.",
        h3_music_en="Emotional swelling orchestral chords signaling an alliance formed."
    ))

    # --------------------------------------------------------------------------
    # Segment 5: EP01-S02-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s5_shots = [
        ms(
            shot_id="EP01-S02-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "青苔水泥牆"],
            blocking_desc="沈洛年靠牆冷淡拍褲管灰塵",
            action_stages=[
                "沈洛年背脊倚靠在陰涼的青苔水泥牆邊",
                "垂眸抬手漫不經心地拍了拍制服褲管沾染的灰塵",
                "單腳微曲站姿放鬆而孤立"
            ],
            observable_expression="面容冷淡平靜，眼神漠然置身事外",
            has_dialogue=False,
            foley="手掌拍擊褲管沙沙灰塵聲",
            h3_action_en="<Subject 1> leans indifferently against the concrete wall in golden sunlight then casually brushes dust off his uniform trousers as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S02-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Suspense_Delay",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="3.5m distance",
            pov_routing="objective",
            movement="trucks right",
            axis_side="right",
            anchor_objects=["沈洛年", "賴一心", "青苔牆面"],
            blocking_desc="賴一心注意到沈洛年手臂傷痕快步迎上",
            action_stages=[
                "賴一心回身望向巷尾陰影中的沈洛年",
                "視線敏銳聚焦於沈洛年左小臂浮現的微紅刮擦傷痕",
                "邁開大步熱情坦蕩地迎上前去"
            ],
            observable_expression="神情由好奇轉為敬佩與欣喜",
            has_dialogue=False,
            foley="球鞋踩過柏油路碎石聲與夕風呼嘯",
            h3_action_en="<Subject 1> turns around noticing the scratches on the boy's forearm then strides briskly forward with curiosity as the camera trucks right",
            h3_camera_en="trucks right"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S02",
        segment_id="EP01-S02-seg01",
        source_scene_id="EP01-S02",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_SHEN"]],
        shots=s5_shots,
        end_state_desc="沈洛年倚牆拍灰，賴一心發現其傷勢並主動走近",
        h3_summary_en="Shen Luonian stands aloof brushing dust from his clothes while Lai Yixin notices his wounds and approaches him.",
        h3_soundscape_en="Gentle dusk wind blowing through the concrete alley with distant city rumble.",
        h3_music_en="Subtle contemplative woodwinds and soft cello notes."
    ))

    # --------------------------------------------------------------------------
    # Segment 6: EP01-S02-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s6_shots = [
        ms(
            shot_id="EP01-S02-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="1.8m eye-level distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="right",
            anchor_objects=["賴一心", "伸出的右手"],
            blocking_desc="賴一心熱情迎上前伸手誇讚",
            action_stages=[
                "賴一心快步走到沈洛年身前半米停步",
                "主動熱情地伸出右手以示結交之意",
                "臉上綻放出毫無戒備的燦爛笑容"
            ],
            observable_expression="熱情洋溢，眼神真摯率直",
            has_dialogue=True,
            speaker="lai-yixin",
            line_verbatim="這位同學，你身手真好！",
            voice_4d_spec="LaiYixin_WarmAdmire_v1",
            foley="停步衣料晃動聲與清朗少年男音",
            h3_action_en="<Subject 1> steps close under the warm sunlight and reaches out his right hand in an open friendly handshake then smiles broadly as the camera dollies in",
            h3_camera_en="dollies in"
        ),
        ms(
            shot_id="EP01-S02-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Reaction_OTS",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.5m distance",
            pov_routing="defensive_reaction_ots",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "賴一心肩背"],
            blocking_desc="沈洛年淡漠注視伸來的手掌無握手之意",
            action_stages=[
                "沈洛年雙眼微垂掠過懸在面前的手掌",
                "身軀未移動分毫依然保持倚牆姿勢",
                "眼神平靜如水絲毫沒有伸手回握的意向"
            ],
            observable_expression="冷靜漠然，防禦性疏離",
            has_dialogue=False,
            foley="夕陽微風吹動洛年額前碎髮聲",
            h3_action_en="past the blurred shoulder of the speaker, the boy keeps his cool gaze fixed without lifting a hand then remains motionless against the wall as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S02",
        segment_id="EP01-S02-seg02",
        source_scene_id="EP01-S02",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_LAI"]],
        shots=s6_shots,
        end_state_desc="賴一心熱情伸手邀結交，沈洛年淡漠不動保持距離",
        h3_summary_en="Lai Yixin warmly offers a handshake complimenting his agility, while Shen Luonian watches with cold indifference.",
        h3_soundscape_en="Soft dusk air with distant traffic drone, highlighting the awkward social pause.",
        h3_music_en="Pizzicato strings contrasting with warm ambient pad."
    ))

    # --------------------------------------------------------------------------
    # Segment 7: EP01-S02-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s7_shots = [
        ms(
            shot_id="EP01-S02-SH05",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年"],
            blocking_desc="沈洛年面無表情拒絕扯上關係",
            action_stages=[
                "沈洛年面無表情地微微搖了搖頭",
                "語氣清冷平淡不帶一絲起伏",
                "視線冷漠移開越過賴一心的肩膀望向虛空"
            ],
            observable_expression="漠然平靜，厭惡麻煩的疏離感",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="我沒興趣，別扯上我。",
            voice_4d_spec="ShenLuonian_ColdDetached_v1",
            foley="微弱嘆氣聲與冷淡少年發音",
            h3_action_en="<Subject 1> shakes his head slightly with a cold indifferent gaze in the sunlight then looks past the stranger without hesitation as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S02-SH06",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="pans left",
            axis_side="left",
            anchor_objects=["沈洛年背影", "黃昏巷口光影"],
            blocking_desc="沈洛年插口袋轉身走向巷口離開",
            action_stages=[
                "沈洛年將雙手從容插進深色制服長褲口袋",
                "側身繞開賴一心徑直邁向夕陽巷口",
                "步伐平穩且毫不遲疑頭也不回地遠去"
            ],
            observable_expression="背影挺拔而透著孤傲冷漠",
            has_dialogue=False,
            foley="腳步踏在石板地上逐漸遠去的節奏聲",
            h3_action_en="<Subject 1> puts both hands deep into his uniform pockets then turns smoothly and walks away toward the glowing alley exit as the camera pans left",
            h3_camera_en="pans left"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S02",
        segment_id="EP01-S02-seg03",
        source_scene_id="EP01-S02",
        lighting_lock=c["LIGHTING_S01_02"],
        ref_images=[c["REF_SCENE_ALLEY"], c["REF_CHAR_SHEN"]],
        shots=s7_shots,
        end_state_desc="沈洛年斷然拒絕組隊邀請，雙手插袋逕自離去",
        h3_summary_en="Shen Luonian flatly refuses to get involved, slipping his hands into his pockets and walking away alone.",
        h3_soundscape_en="Fading footsteps in the dusk alley with quiet wind whispers.",
        h3_music_en="Solitary melancholic piano notes echoing his lone wolf attitude."
    ))

    # --------------------------------------------------------------------------
    # Segment 8: EP01-S03-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s8_shots = [
        ms(
            shot_id="EP01-S03-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m eye-level distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "綠色美耐皿餐桌", "保麗龍餐盤"],
            blocking_desc="沈洛年在快餐店桌前大口扒飯",
            action_stages=[
                "沈洛年端著免洗保麗龍餐盤坐在快餐店綠色方桌前",
                "右手握筷大口將米飯送入口中咀嚼充飢",
                "周圍擺放著零星的空便當盒與免洗湯碗"
            ],
            observable_expression="專注進食，神情放鬆平常",
            has_dialogue=False,
            foley="筷子扒飯碰觸保麗龍聲與咀嚼吞嚥聲",
            h3_action_en="<Subject 1> sits by a pale green cafeteria table under fluorescent ceiling light then quietly eats rice with chopsticks from a disposable plate as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S03-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Suspense_Delay",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="4.0m distance",
            pov_routing="objective",
            movement="tilts up",
            axis_side="center",
            anchor_objects=["快餐店天花板", "長條日光燈管"],
            blocking_desc="天花板日光燈管異樣閃爍發出電流爆鳴",
            action_stages=[
                "快餐店天花板懸掛的雙管日光燈驟然頻繁明滅",
                "電磁整流器發出刺耳的高頻滋滋電流爆鳴聲",
                "餐廳光影忽明忽暗投下不祥的陰森籠罩感"
            ],
            observable_expression="環境光影突變的不祥氣氛",
            has_dialogue=False,
            foley="日光燈整流器劇烈滋滋電流爆鳴與鎢絲震顫聲",
            h3_action_en="overhead fluorescent tube lights flicker violently with buzzing electricity arcs then cast rapid strobe shadows over the diner as the camera tilts up",
            h3_camera_en="tilts up"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S03",
        segment_id="EP01-S03-seg01",
        source_scene_id="EP01-S03",
        lighting_lock=c["LIGHTING_S03_FASTFOOD"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s8_shots,
        end_state_desc="沈洛年用餐時，快餐店頂棚日光燈突發異樣劇烈閃爍",
        h3_summary_en="While Shen Luonian eats quietly in the cafeteria, the fluorescent ceiling lights suddenly flicker ominously with buzzing electricity.",
        h3_soundscape_en="Diner hum suddenly interrupted by harsh electric buzzing and flickering light tube crackles.",
        h3_music_en="Sudden discordant synthesizer drone heralding sudden danger."
    ))

    # --------------------------------------------------------------------------
    # Segment 9: EP01-S03-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s9_shots = [
        ms(
            shot_id="EP01-S03-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Suspense_Delay",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="pans right",
            axis_side="left",
            anchor_objects=["廚房薄木隔間門", "瓷磚地板"],
            blocking_desc="廚房傳來淒厲慘叫與鍋鏟砸地巨響",
            action_stages=[
                "餐廳後方廚房薄木門內傳出廚師刺耳的淒厲慘嚎",
                "厚重鐵鍋與金屬鍋鏟砸在瓷磚地板上發出沉悶巨響",
                "油水飛濺聲伴隨劇烈撞擊震動了木板隔間"
            ],
            observable_expression="突發慘劇的驚駭慌亂",
            has_dialogue=False,
            foley="淒厲廚房慘叫、沉重鐵鍋摔砸翻滾與盤碗爆裂聲",
            h3_action_en="loud screams erupt behind the wooden kitchen partition as heavy metal pots clatter onto the tiled floor then liquids splatter across the doorway as the camera pans right",
            h3_camera_en="pans right"
        ),
        ms(
            shot_id="EP01-S03-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "停滯的筷子"],
            blocking_desc="沈洛年停箸皺眉心頭升起不祥預感",
            action_stages=[
                "沈洛年筷子停在半空中眉頭猛然擰緊",
                "下意識抬頭目光如刀鋒般刺向後廚方向",
                "咀嚼動作驟停喉結微動進入警戒狀態"
            ],
            observable_expression="眉頭緊鎖，眼神高度戒備",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="又是這怪動靜？",
            voice_4d_spec="ShenLuonian_AlertTense_v1",
            foley="停筷輕磕聲與低沉少年戒備嗓音",
            h3_action_en="<Subject 1> freezes his chopsticks mid-air beneath flickering tube lights then sharply turns his intense dark eyes toward the kitchen as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S03",
        segment_id="EP01-S03-seg02",
        source_scene_id="EP01-S03",
        lighting_lock=c["LIGHTING_S03_FASTFOOD"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s9_shots,
        end_state_desc="後廚傳來金屬翻倒與慘叫，沈洛年停筷皺眉戒備",
        h3_summary_en="Horrified screams and crashing cookware resound from the kitchen, making Shen Luonian halt his chopsticks in sharp suspicion.",
        h3_soundscape_en="Terrified human shriek, metal pots tumbling across tiled floor, heavy silence.",
        h3_music_en="Staccato strings building heart-thumping suspense."
    ))

    # --------------------------------------------------------------------------
    # Segment 10: EP01-S03-seg03 (8.0s, 3 shots: 2.8s + 2.7s + 2.5s)
    # --------------------------------------------------------------------------
    s10_shots = [
        ms(
            shot_id="EP01-S03-SH05",
            start_time=0.0,
            duration=2.8,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="center",
            anchor_objects=["粉碎的木隔間", "食人巨鼠"],
            blocking_desc="隔間牆轟然爆碎，食人巨鼠如黑砲彈撲出",
            action_stages=[
                "薄木板隔間牆在狂暴怪力下轟然炸碎木屑漫天飛濺",
                "一米多長長滿粗黑硬毛的食人巨鼠如黑色砲彈凌空撲出",
                "落地四爪狠狠扒扣地磚發出刺耳刮擦"
            ],
            observable_expression="嗜血狂暴之兇煞威壓",
            has_dialogue=False,
            foley="木板爆碎轟鳴、尖銳怪叫與爪子刮擦瓷磚刺耳聲",
            h3_action_en="the plywood wall splinters outward under fluorescent lamps as a monstrous dark-furred giant rat bursts into the cafeteria then digs its sharp black claws into the tiles as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S03-SH06",
            start_time=2.8,
            duration=2.7,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="left",
            anchor_objects=["食人巨鼠", "受害者婦人", "血染瓷磚"],
            blocking_desc="巨鼠獠牙咬穿婦人頸項，鮮血飛濺地磚",
            action_stages=[
                "巨鼠閃電前竄黃色長獠牙狠狠咬入婦人後頸",
                "強大衝擊力將帶童婦人當場撲倒在碎裂瓷磚上",
                "婦人身軀軟倒在地鮮血迅速在瓷磚縫隙擴散蔓延"
            ],
            observable_expression="血腥兇殘的捕殺獵殺",
            has_dialogue=False,
            foley="沉悶肉體撕咬聲、婦人短促慘哼與血液噴濺聲",
            h3_action_en="the monstrous beast lunges forward clamping its long curved incisors directly through the victim's neck then pins her to the tiled floor as blood spreads into tile cracks as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP01-S03-SH07",
            start_time=5.5,
            duration=2.5,
            dramatic_beat_type="Dramatic_Core",
            shot_size="CU",
            focal_length="85mm",
            physical_distance="1.5m close distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="left",
            anchor_objects=["食人巨鼠首級", "赤紅眼珠"],
            blocking_desc="巨鼠滿嘴鮮血轉動血眼死鎖沈洛年",
            action_stages=[
                "滿嘴鮮血的巨鼠緩緩自婦人屍體上方抬起醜陋鼠首",
                "兩顆血滴般的猩紅眼珠轉向左側兩步外的沈洛年",
                "粉紅肉柱長尾在地面如毒蛇般盤繞蓄勢待發"
            ],
            observable_expression="赤紅眼珠冰冷嗜血，殺意死死鎖定",
            has_dialogue=False,
            foley="低沉喉音嘶鳴、滴血水滴聲與長尾摩擦地磚聲",
            h3_action_en="the rat slowly lifts its gory snout under cold ceiling lights and turns its glowing crimson eyes directly toward the nearby boy then swishes its muscular tail as the camera dollies in",
            h3_camera_en="dollies in"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP01-S03",
        segment_id="EP01-S03-seg03",
        source_scene_id="EP01-S03",
        lighting_lock=c["LIGHTING_S03_FASTFOOD_FIGHT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CREATURE_RAT"]],
        shots=s10_shots,
        end_state_desc="巨鼠破牆咬穿婦人，赤紅血眼轉向兩步外的沈洛年（懸疑斷點）",
        h3_summary_en="The giant rat shatters the wooden partition, brutally kills a woman, and locks its bloody crimson gaze onto Shen Luonian.",
        h3_soundscape_en="Bone-chilling rodent hissing, bone snaps, wet blood splatters, dead silence of terror.",
        h3_music_en="Massive dramatic cliffhanger brass blast and descending horror drone."
    ))

    return segments
