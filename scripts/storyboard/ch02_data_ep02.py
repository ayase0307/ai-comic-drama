#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ch02_data_ep02.py
第二章 EP02（慢速世界與食人巨鼠）10 個分段資料定義
嚴格遵守《噩盡島》實戰定案：每段 8.0s，每鏡 >= 2.5s，力學三要素具體，台詞 100% 逐字吻合。
"""

def get_ep02_segments(helpers):
    ms = helpers["make_shot"]
    mseg = helpers["make_segment"]
    c = helpers["constants"]

    segments = []

    # --------------------------------------------------------------------------
    # Segment 1: EP02-S01-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s1_shots = [
        ms(
            shot_id="EP02-S01-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["受驚幼童", "倒地婦人", "血染瓷磚"],
            blocking_desc="幼童跌坐血泊撕心裂肺大哭",
            action_stages=[
                "幼童跌坐在碎瓷磚上雙手死死抓著母親沾血衣襟",
                "驚恐萬狀地發出撕心裂肺的嚎哭與尖叫",
                "渾身劇烈發抖無助地蜷縮在血泊邊緣"
            ],
            observable_expression="幼童極度驚恐與撕心裂肺的悲痛",
            has_dialogue=False,
            foley="幼童淒厲嚎哭哭喊聲與血液滴落聲",
            h3_action_en="a small child collapses onto the bloodstained tiles under flickering ceiling lights then clutches his fallen mother's clothes in sheer panic as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP02-S01-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="right",
            anchor_objects=["食人巨鼠肉柱長尾", "不鏽鋼圓凳"],
            blocking_desc="巨鼠粗壯肉柱長尾橫掃抽打而來",
            action_stages=[
                "巨鼠粗壯粉紅如肉柱般的長尾猛然自地面弓起蓄力",
                "長尾帶著撕裂空氣的銳利呼嘯橫空向幼童攔腰狠抽而去",
                "沿途帶翻兩張不鏽鋼金屬凳刮擦出刺耳火星"
            ],
            observable_expression="巨獸尾部肌肉暴起致命抽殺",
            has_dialogue=False,
            foley="肉柱破空呼嘯聲與金屬鐵凳翻倒撞擊地磚巨響",
            h3_action_en="the monstrous rat coils its thick fleshy muscular tail then whips it horizontally across the room shattering steel stools as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S01",
        segment_id="EP02-S01-seg01",
        source_scene_id="EP02-S01",
        lighting_lock=c["LIGHTING_S03_FASTFOOD_FIGHT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CREATURE_RAT"]],
        shots=s1_shots,
        end_state_desc="幼童在血泊旁嚎哭，巨鼠肉柱長尾呼嘯抽擊",
        h3_summary_en="The toddler weeps beside his fallen mother as the giant rat whips its muscular tail violently toward him.",
        h3_soundscape_en="Harrowing toddler shrieks and heavy whiplash whooshes cracking through the room.",
        h3_music_en="Pounding industrial percussion and screeching horror strings."
    ))

    # --------------------------------------------------------------------------
    # Segment 2: EP02-S01-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s2_shots = [
        ms(
            shot_id="EP02-S01-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.0m distance",
            pov_routing="clear_impact_90deg",
            movement="trucks left",
            axis_side="left",
            anchor_objects=["沈洛年", "不鏽鋼圓鐵凳", "受驚幼童"],
            blocking_desc="沈洛年拽開小孩，掄起圓凳暴喝砸向鼠首",
            action_stages=[
                "沈洛年左手閃電探出抓住幼童衣領猛力向後拖開",
                "右手五指青筋暴起順勢抓起重達數公斤的不鏽鋼圓鐵凳",
                "借腰部扭轉暴喝著將鐵凳當頭狂暴砸向巨鼠首級"
            ],
            observable_expression="面容因狂暴發力而緊繃，腎上腺素爆發",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="幹！給我滾開！",
            voice_4d_spec="ShenLuonian_FuriousShout_v1",
            foley="扯動衣物聲、沉重金屬揮舞破空聲與少年暴喝",
            h3_action_en="<Subject 1> yanks the child behind him then swings a heavy stainless steel stool overhead with furious force as the camera trucks left",
            h3_camera_en="trucks left"
        ),
        ms(
            shot_id="EP02-S01-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="right",
            anchor_objects=["圓鐵凳面", "食人巨鼠側臉", "翻倒餐桌"],
            blocking_desc="鐵凳重砸鼠臉，巨鼠慘叫側翻撞翻餐桌",
            action_stages=[
                "厚重金屬凳面狠狠砸在巨鼠猙獰的左側臉頰骨骼上",
                "金屬發出震耳欲聾的嗡鳴巨響伴隨骨裂沉悶回音",
                "巨鼠受強大橫向衝擊慘嘶著連翻數圈撞倒兩張餐桌"
            ],
            observable_expression="巨怪受創痛楚慘嘶",
            has_dialogue=False,
            foley="厚重金屬砸擊骨骼悶響、金屬回鳴與巨獸尖銳慘叫",
            h3_action_en="the round steel stool smashes brutally against the side of the rat's skull under flickering fluorescent tube lights then sends the monster rolling over smashed tables as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S01",
        segment_id="EP02-S01-seg02",
        source_scene_id="EP02-S01",
        lighting_lock=c["LIGHTING_S03_FASTFOOD_FIGHT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s2_shots,
        end_state_desc="沈洛年救下幼童，掄圓凳狠砸巨鼠頭部將其擊退側翻",
        h3_summary_en="Shen Luonian yanks the boy away and brutally smashes a steel stool onto the monster's skull, sending it crashing into tables.",
        h3_soundscape_en="Deafening metallic clang of impact, shattered wood, agonized beast screeching.",
        h3_music_en="Aggressive battle percussion slamming into high gear."
    ))

    # --------------------------------------------------------------------------
    # Segment 3: EP02-S01-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s3_shots = [
        ms(
            shot_id="EP02-S01-SH05",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="1.8m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "受驚幼童"],
            blocking_desc="沈洛年推小孩逃跑指示往門口去",
            action_stages=[
                "沈洛年反手一把將跌坐在地的幼童推向身後走道",
                "雙眼死死盯著爬起的巨鼠頭也不回低喝指示",
                "身軀牢牢擋在幼童與怪物之間阻斷殺戮線路"
            ],
            observable_expression="眼神冷冽堅毅，專注護衛身後",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="小孩別哭，快往門口跑！",
            voice_4d_spec="ShenLuonian_FirmUrgent_v1",
            foley="腳步推移聲與低沉急促命令聲",
            h3_action_en="<Subject 1> pushes the weeping toddler firmly toward the exit beneath the flickering tube lights then positions his body as a protective shield as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP02-S01-SH06",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Suspense_Delay",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="3.0m distance",
            pov_routing="objective",
            movement="static",
            axis_side="center",
            anchor_objects=["沈洛年背影", "染血圓鐵凳", "快餐店大門"],
            blocking_desc="幼童奔向門口，沈洛年橫凳擋在前方面對怪物",
            action_stages=[
                "幼童連滾帶爬哭喊著撲向快餐店敞開的玻璃大門",
                "沈洛年雙手橫握染血的圓鐵凳腳微曲下沉重心",
                "呼吸粗重但雙臂如同鑄鐵般紋絲不動護住退路"
            ],
            observable_expression="背脊微弓，身形宛如不可撼動之屏障",
            has_dialogue=False,
            foley="幼童跌跌撞撞奔跑腳步聲與粗重喘息聲",
            h3_action_en="the child scrambles across the floor toward the glass door as the boy stands firmly holding the metal stool ready for combat as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S01",
        segment_id="EP02-S01-seg03",
        source_scene_id="EP02-S01",
        lighting_lock=c["LIGHTING_S03_FASTFOOD_FIGHT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s3_shots,
        end_state_desc="幼童成功跑向大門，沈洛年橫握圓凳嚴陣以待",
        h3_summary_en="Shen Luonian urges the child to flee to the doors while holding his steel stool firmly to guard the line.",
        h3_soundscape_en="Child's hurried footsteps retreating, tense heavy breathing, flickering lamp hum.",
        h3_music_en="Tense low-end brass drone maintaining defensive tension."
    ))

    # --------------------------------------------------------------------------
    # Segment 4: EP02-S02-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s4_shots = [
        ms(
            shot_id="EP02-S02-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="35mm",
            physical_distance="2.5m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="right",
            anchor_objects=["食人巨鼠雙爪", "碎木屑"],
            blocking_desc="巨鼠暴起雙爪撲咬而來",
            action_stages=[
                "巨鼠黑硬鋼毛炸立，後肢蹬碎地磚猛然彈射飛躍",
                "兩支漆黑彎鉤前爪撕裂空氣由上而下當頭抓下",
                "腥臭獠牙大張直奔沈洛年咽喉要害撲咬而至"
            ],
            observable_expression="巨怪狂暴兇殘之撲殺威勢",
            has_dialogue=False,
            foley="地磚蹬碎炸裂聲、爪刃破空銳響與腥臭嘶吼",
            h3_action_en="the giant rat leaps aggressively through the air with razor-sharp black claws lunging downward then opens its yellow curved teeth as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP02-S02-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="CU",
            focal_length="85mm",
            physical_distance="1.0m close distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="left",
            anchor_objects=["沈洛年面容", "定格的空中木屑"],
            blocking_desc="沈洛年感官世界減速，巨鼠半空緩慢滯空",
            action_stages=[
                "沈洛年雙瞳急速收縮泛起微弱奇異光芒",
                "空中翻滾的碎木屑與閃爍燈影驟然近乎定格靜止",
                "巨鼠在半空以肉眼可辨的極緩慢速度滯空滑行"
            ],
            observable_expression="震驚錯愕，隨後轉為超常專注感知",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="速度……怎麼變慢了？",
            voice_4d_spec="ShenLuonian_PuzzledBreath_v1",
            foley="高頻心跳耳鳴轟鳴與時間減速特異水滴擴散音",
            h3_action_en="<Subject 1> observes the airborne splinters freezing in mid-air under ethereal light as time slows down then whispers in wonder as the camera dollies in",
            h3_camera_en="dollies in"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S02",
        segment_id="EP02-S02-seg01",
        source_scene_id="EP02-S02",
        lighting_lock=c["LIGHTING_S03_TIME_DILATION"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s4_shots,
        end_state_desc="巨鼠凌空撲殺，沈洛年瞳孔收縮進入時間減速超感境界",
        h3_summary_en="The rat launches into a fatal pounce, but Shen Luonian's perception slows time to a crawl as he tracks every motion.",
        h3_soundscape_en="Muffled time-warp whoosh, deep heartbeat pulse slowing down to half speed.",
        h3_music_en="Ethereal glass harmonica tone and slow ticking time clock."
    ))

    # --------------------------------------------------------------------------
    # Segment 5: EP02-S02-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s5_shots = [
        ms(
            shot_id="EP02-S02-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.2m distance",
            pov_routing="clear_impact_90deg",
            movement="trucks left",
            axis_side="left",
            anchor_objects=["沈洛年", "圓鐵凳", "翻倒方桌"],
            blocking_desc="沈洛年側身避爪，圓凳頂腹借力凌空側翻",
            action_stages=[
                "沈洛年沉腰向右微擰毫釐之間避開懸空下落的利爪",
                "右手圓凳精準頂在巨鼠柔軟腹部作為槓桿支點",
                "雙腿發力凌空側翻輕巧越過翻倒的綠色方桌"
            ],
            observable_expression="動作精準靈動，行雲流水",
            has_dialogue=False,
            foley="身形避讓破空風聲、金屬頂擊悶響與平穩落定聲",
            h3_action_en="<Subject 1> sways his torso smoothly in warm light avoiding the falling claws then vaults lightly over the table with his steel stool as the camera trucks left",
            h3_camera_en="trucks left"
        ),
        ms(
            shot_id="EP02-S02-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.5m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "斜指圓凳"],
            blocking_desc="沈洛年平穩落定，嘴角浮現自信微笑",
            action_stages=[
                "沈洛年雙腳平穩落定在地磚上側身卸去慣性衝力",
                "右手圓凳斜指向地目光如炬鎖定落地巨鼠",
                "嘴角微抿浮現出一絲掌控局面的自信"
            ],
            observable_expression="神情銳利，自信鎮定",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="看清楚了，能躲開！",
            voice_4d_spec="ShenLuonian_ConfidentCalm_v1",
            foley="衣角擺動停頓聲與堅定呼吸收束聲",
            h3_action_en="<Subject 1> lands solidly on both feet holding the stool ready under the lamp light then speaks with cool clarity as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S02",
        segment_id="EP02-S02-seg02",
        source_scene_id="EP02-S02",
        lighting_lock=c["LIGHTING_S03_FASTFOOD_FIGHT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s5_shots,
        end_state_desc="沈洛年瀟灑側翻避開撲咬，確立能躲開妖物速度",
        h3_summary_en="Shen Luonian smoothly dodges the strike, vaults over a table, and realizes he can clearly evade the creature.",
        h3_soundscape_en="Light landing thud on tile floor, steady deep breath, diner room hum.",
        h3_music_en="Confident rhythmic synth bassline driving forward."
    ))

    # --------------------------------------------------------------------------
    # Segment 6: EP02-S03-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s6_shots = [
        ms(
            shot_id="EP02-S03-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="4.0m distance",
            pov_routing="objective",
            movement="pans right",
            axis_side="left",
            anchor_objects=["警察甲", "快餐店玻璃門", "配槍"],
            blocking_desc="警察撞開玻璃門拔槍衝入大廳",
            action_stages=[
                "快餐店玻璃門被兩名身穿制服的巡警猛力撞開",
                "兩警拔出黑色手槍雙手握持指向大廳中央的巨獸",
                "警員胸膛劇烈起伏滿臉蒼白駭然"
            ],
            observable_expression="警員滿臉蒼白駭然與極度戒備",
            has_dialogue=False,
            foley="玻璃門猛烈撞擊牆壁巨響與沉重警靴奔踏聲",
            h3_action_en="two uniformed police officers kick open the glass entrance under street light glare then raise their black service pistols in shock as the camera pans right",
            h3_camera_en="pans right"
        ),
        ms(
            shot_id="EP02-S03-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["警察甲", "槍口火舌"],
            blocking_desc="警察扣動扳機大吼命令站住",
            action_stages=[
                "領頭警員雙臂緊繃槍口瞄準巨鼠首級大吼警告",
                "食指下意識連續扣動手槍扳機槍口噴吐出刺目火舌",
                "彈殼連綿飛出跌落在門口水磨石地板上清脆作響"
            ],
            observable_expression="慌亂驚恐中的歇斯底里狂吼",
            has_dialogue=True,
            speaker="policeman-a",
            line_verbatim="站住！別動！",
            voice_4d_spec="Policeman_PanicShout_v1",
            foley="震耳欲聾的手槍槍擊爆鳴與黃銅彈殼墜地脆響",
            h3_action_en="the lead officer screams in panic under flashlight beams then fires repeatedly as bright muzzle flashes illuminate his face as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S03",
        segment_id="EP02-S03-seg01",
        source_scene_id="EP02-S03",
        lighting_lock=c["LIGHTING_S03_POLICE_SHOOT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s6_shots,
        end_state_desc="警察撞門衝入拔槍狂射，槍火撕裂昏暗餐廳",
        h3_summary_en="Police officers burst through the doors and open fire frantically with service pistols at the monstrous beast.",
        h3_soundscape_en="Repeated concussive 9mm gunshots, brass casings clinking on floor, panicked police yells.",
        h3_music_en="Frantic urban siren motifs and intense brass chords."
    ))

    # --------------------------------------------------------------------------
    # Segment 7: EP02-S03-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s7_shots = [
        ms(
            shot_id="EP02-S03-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="clear_impact_90deg",
            movement="static",
            axis_side="right",
            anchor_objects=["食人巨鼠軀幹", "彈孔痕跡"],
            blocking_desc="鉛彈射入鼠身爆出彈孔卻絲毫不流血",
            action_stages=[
                "數道黑色高速鉛彈軌跡狠狠射入巨鼠軀幹與肌肉",
                "皮肉表面凹陷爆開焦黑彈孔卻絲毫不見血液湧出",
                "巨鼠軀體僅被動能阻滯後滑半步肌肉旋即將彈孔緊縮封閉"
            ],
            observable_expression="妖獸皮肉刀槍不入的詭異蠕動",
            has_dialogue=False,
            foley="子彈打入厚重死肉沉悶聲與肌肉緊縮怪聲",
            h3_action_en="lead bullets punch directly into the thick rat hide beneath flashlights then the wound holes seal dryly without bleeding as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
        ms(
            shot_id="EP02-S03-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="CU",
            focal_length="85mm",
            physical_distance="1.2m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["警察甲煞白面孔", "顫抖的槍口"],
            blocking_desc="警察崩潰狂喊子彈無效不流血",
            action_stages=[
                "開槍警員雙手劇烈顫抖看著毫髮無損的怪物狂喊",
                "恐懼蔓延至整張煞白的面容腳步下意識向後踉蹌倒退",
                "手槍險些失手脫落眼神陷入崩潰"
            ],
            observable_expression="信念瓦解，眼神陷入不可置信之絕望",
            has_dialogue=True,
            speaker="policeman-a",
            line_verbatim="子彈沒用！它根本不流血！",
            voice_4d_spec="Policeman_DespairCry_v1",
            foley="急促倒退碎步聲與破音恐懼嘶喊",
            h3_action_en="the officer staggers backwards under cold ceiling light then screams in utter disbelief as terror completely overtakes him as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S03",
        segment_id="EP02-S03-seg02",
        source_scene_id="EP02-S03",
        lighting_lock=c["LIGHTING_S03_POLICE_SHOOT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CREATURE_RAT"]],
        shots=s7_shots,
        end_state_desc="子彈擊中巨鼠不流血無效，警察陷入崩潰絕望",
        h3_summary_en="The bullets penetrate the giant rat without drawing blood, driving the armed police officers into horrified despair.",
        h3_soundscape_en="Empty gun clicks, dry bullet impacts, trembling horrified breathing.",
        h3_music_en="Dissonant low strings and despairing ambient sub-bass."
    ))

    # --------------------------------------------------------------------------
    # Segment 8: EP02-S03-seg03 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s8_shots = [
        ms(
            shot_id="EP02-S03-SH05",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="4.5m distance",
            pov_routing="objective",
            movement="trucks left",
            axis_side="center",
            anchor_objects=["破碎落地窗", "食人巨鼠", "夜雨街景"],
            blocking_desc="巨鼠長尾掃碎落地窗，竄入夜雨遁逃",
            action_stages=[
                "巨鼠仰起血淋淋的鼠首發出一聲尖銳刺耳的暴戾怪嘯",
                "粗壯長尾猛然一甩撞碎臨街整面厚重落地玻璃",
                "龐大黑影縱身躍出窗欞破洞閃電般消融在傾盆夜雨中"
            ],
            observable_expression="凶殘怪獸遁逃時的狂暴怪相",
            has_dialogue=False,
            foley="落地大玻璃崩潰粉碎轟鳴與狂風夜雨灌入聲",
            h3_action_en="the monstrous rodent roars angrily under the street lamps then shatters the floor-to-ceiling glass wall with its tail and escapes into the rainy night as the camera trucks left",
            h3_camera_en="trucks left"
        ),
        ms(
            shot_id="EP02-S03-SH06",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MCU",
            focal_length="85mm",
            physical_distance="1.5m close distance",
            pov_routing="objective",
            movement="static",
            axis_side="left",
            anchor_objects=["沈洛年", "垂下的圓鐵凳"],
            blocking_desc="沈洛年退後心悸低語槍械殺不死妖怪",
            action_stages=[
                "沈洛年緩緩垂下握著圓鐵凳的手臂後退半步靠在立柱",
                "注視著滿地碎玻璃與空彈殼低聲自語",
                "眼神中浮現出對常識瓦解的深深震撼"
            ],
            observable_expression="震撼心悸，世界觀顛覆的恍惚感",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="連槍都殺不死妖怪？",
            voice_4d_spec="ShenLuonian_ShockedWhisper_v1",
            foley="夜雨呼嘯灌入餐廳聲與少年低沉喃喃",
            h3_action_en="<Subject 1> lowers the metal stool in the cold breeze under lamp light then mutters in deep astonishment as rain drenches the floor as the camera holds a static shot",
            h3_camera_en="holds a static shot"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S03",
        segment_id="EP02-S03-seg03",
        source_scene_id="EP02-S03",
        lighting_lock=c["LIGHTING_S03_POLICE_SHOOT"],
        ref_images=[c["REF_SCENE_FASTFOOD"], c["REF_CHAR_SHEN"]],
        shots=s8_shots,
        end_state_desc="巨鼠撞破玻璃逃遁，沈洛年因槍械無效深感震驚",
        h3_summary_en="The rat smashes through the glass wall into the dark rain, leaving Shen Luonian stunned by the supernatural creature's resilience.",
        h3_soundscape_en="Torrential rainfall rushing through the broken window frame, distant police sirens wailing.",
        h3_music_en="Solemn somber string progression marking the loss of ordinary security."
    ))

    # --------------------------------------------------------------------------
    # Segment 9: EP02-S04-seg01 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s9_shots = [
        ms(
            shot_id="EP02-S04-SH01",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Expository_Fast",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.5m distance",
            pov_routing="objective",
            movement="dollies in",
            axis_side="left",
            anchor_objects=["沈洛年", "板橋車站石柱"],
            blocking_desc="沈洛年奔入車站大廳扶柱大口喘息",
            action_stages=[
                "沈洛年推開板橋車站旋轉門快步奔入寬闊大廳",
                "單手扶著厚重花崗岩立柱躬身劇烈喘息擦拭額頭冷汗",
                "回望身後安靜的夜色稍稍鬆下一口氣"
            ],
            observable_expression="疲憊劇烈喘息，短暫脫險的釋然",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="甩掉那隻大老鼠了。",
            voice_4d_spec="ShenLuonian_RelievedPant_v1",
            foley="旋轉門轉動嘎吱聲、沉重急促喘息聲與腳步停頓",
            h3_action_en="<Subject 1> runs into the vast station hall under ambient white ceiling lights then rests his hand against a stone pillar catching his breath as the camera dollies in",
            h3_camera_en="dollies in"
        ),
        ms(
            shot_id="EP02-S04-SH02",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Suspense_Delay",
            shot_size="MLS",
            focal_length="35mm",
            physical_distance="4.0m distance",
            pov_routing="objective",
            movement="tilts down",
            axis_side="center",
            anchor_objects=["車站吊燈", "掀飛的鑄鐵水溝蓋", "下水道怪霧"],
            blocking_desc="頂燈驟然狂閃，地面重型水溝蓋砰然掀飛",
            action_stages=[
                "大廳頂部數排吊燈突然毫無徵兆地瘋狂明滅閃爍",
                "地面巨大的鑄鐵排水溝蓋轟隆一聲被狂暴氣浪掀飛半空",
                "刺鼻的陰冷下水道怪霧自孔洞中狂湧而出"
            ],
            observable_expression="心頭猛然一緊，雙目圓睜驚愕",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="等等，燈又在閃？",
            voice_4d_spec="ShenLuonian_SuddenAlert_v1",
            foley="吊燈急促閃爍滋滋聲、鑄鐵重蓋炸飛砸地巨響與毒霧噴發聲",
            h3_action_en="the overhead station lamps suddenly flicker wildly then a massive iron manhole cover blows off the floor releasing misty vapours as the camera tilts down",
            h3_camera_en="tilts down"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S04",
        segment_id="EP02-S04-seg01",
        source_scene_id="EP02-S04",
        lighting_lock=c["LIGHTING_S04_STATION_SLIME"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SHEN"]],
        shots=s9_shots,
        end_state_desc="洛年剛入車站喘息，頂燈再度狂閃，水溝蓋爆飛",
        h3_summary_en="Shen Luonian catches his breath inside Banqiao Station, but the lights flicker again as an iron manhole cover blasts open.",
        h3_soundscape_en="Station hall echo, violent electrical buzz, massive iron bang crashing against marble tiles.",
        h3_music_en="Sudden rising sinister low brass chord."
    ))

    # --------------------------------------------------------------------------
    # Segment 10: EP02-S04-seg02 (8.0s, 2 shots: 4.0s + 4.0s)
    # --------------------------------------------------------------------------
    s10_shots = [
        ms(
            shot_id="EP02-S04-SH03",
            start_time=0.0,
            duration=4.0,
            dramatic_beat_type="Combat_Impact",
            shot_size="ELS",
            focal_length="24mm",
            physical_distance=">8m wide panorama",
            pov_routing="clear_impact_90deg",
            movement="trucks right",
            axis_side="center",
            anchor_objects=["果凍史萊姆巨怪", "翻捲肉裙", "四散旅客"],
            blocking_desc="果凍巨怪自孔洞膨脹至五公尺寬，肉裙巨浪罩向人質",
            action_stages=[
                "藍白色半透明如膠質的龐然大物自孔洞瘋狂湧出",
                "如發酵麵團般急速膨脹至五公尺寬二公尺高",
                "軀幹翻捲出數道如滔天巨浪般的肉裙向四周逃散群眾席捲籠罩"
            ],
            observable_expression="不可名狀異界巨怪之極致威壓",
            has_dialogue=False,
            foley="黏液滑膩湧動翻江倒海聲、肉裙破空席捲聲與群眾驚叫",
            h3_action_en="a colossal translucent blue-white slime creature erupts through the floor under white lamps and swells rapidly five meters wide then casts skirt-like tentacles over civilians as the camera trucks right",
            h3_camera_en="trucks right"
        ),
        ms(
            shot_id="EP02-S04-SH04",
            start_time=4.0,
            duration=4.0,
            dramatic_beat_type="Dramatic_Core",
            shot_size="MS",
            focal_length="50mm",
            physical_distance="2.0m distance",
            pov_routing="objective",
            movement="pans left",
            axis_side="left",
            anchor_objects=["沈洛年", "避險石柱"],
            blocking_desc="沈洛年拔腿後撤驚駭大喊",
            action_stages=[
                "沈洛年瞳孔劇烈放大倒映出滔天翻滾的藍白巨浪",
                "毫不猶豫拔腿向後飛速倒退躍開數步避開膠質波及",
                "右手緊扣立柱邊緣滿臉駭然地望著眼前噩夢異象"
            ],
            observable_expression="駭然驚愕，果斷疾退求生",
            has_dialogue=True,
            speaker="shen-luonian",
            line_verbatim="這怪物又是什麼鬼！",
            voice_4d_spec="ShenLuonian_AppalledRetreat_v1",
            foley="球鞋急促摩擦花崗岩聲與震撼驚呼",
            h3_action_en="<Subject 1> leaps backward in terror as the blue-white gelatinous wave looms in the station lighting then yells in horror as the camera pans left",
            h3_camera_en="pans left"
        ),
    ]
    segments.append(mseg(
        project_id="ejd-ch02",
        scene_id="EP02-S04",
        segment_id="EP02-S04-seg02",
        source_scene_id="EP02-S04",
        lighting_lock=c["LIGHTING_S04_STATION_SLIME"],
        ref_images=[c["REF_SCENE_STATION"], c["REF_CHAR_SHEN"]],
        shots=s10_shots,
        end_state_desc="果凍巨怪吞噬旅客，沈洛年駭然疾退（懸疑斷點）",
        h3_summary_en="The colossal slime creature erupts from the drain swallowing travelers, forcing Shen Luonian into a desperate retreat.",
        h3_soundscape_en="Massive wet gelatinous undulations, distant crowd panics, cold transit hall echoes.",
        h3_music_en="Terrifying orchestral climax and suspense cliffhanger crescendo."
    ))

    return segments
