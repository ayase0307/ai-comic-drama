# 運鏡選用指南：場景意圖 → 運鏡（PR-14d）

階段 4 導演分鏡時，每鏡先寫 `shot_intent`，再依本表選 `camera_optics.move_preset`，並在 `choice_why` 寫選用理由。
階段 5 編譯器展開 preset；`scripts/storyboard/move_lint.py` 會對不當組合發 warning。
驗證狀態來自 Colab 第 1–3 輪實測（work/camera-moves/results.csv）；家機 2–3 秒子鏡的可信度約降半級。

## 節奏成本
- 一鏡一個運鏡；一段最多 1–2 個強運鏡（`strong: True` 的 preset）。
- 最大衝擊鏡、對白 CU／MCU、纏繞特寫、三主體以上、≤2 秒子鏡、段首／鏡首接上一鏡終態：不用強運鏡。
- 手持不能拿來假裝主體在動；震屏是特效（要寫衰減），不是運鏡。

## 情緒
| 情緒 | 首選 | 備選 | 禁用／理由 |
|---|---|---|---|
| 緊張、逼近 | 緩推 push-in（專案驗證） | snorricam | 對白 CU 不加強運鏡 |
| 揭露 | ots_reveal、aerial_pullback | high_angle_tilt_down | 要寫完整場景段，否則灰底滲入 |
| 震驚、失衡 | dolly_zoom（可用） | yoyo_zoom | 2 秒以下不用 |
| 回憶、恍惚 | eyes_in | dutch_canted（寫畫面結果） | 不用 roll 式荷蘭角 |
| 孤立、渺小 | top_down_rise、aerial_pullback | super_dolly_in | 全程朝下，禁止漸變 |

## 劇情節點
| 節點 | 首選 | 備選 | 禁用／理由 |
|---|---|---|---|
| 開場建立 | aerial_pullback | super_dolly_in | 場景要先寫進提示詞 |
| 角色登場 | ots_reveal | high_angle_tilt_down | 重申參考服裝，避免過肩換裝 |
| 對峙 | 固定機位 | 緩推 | 不用環繞 |
| 追逐 | 後退跟拍／追逐跟拍（專案驗證） | snorricam | 三主體以上降級為固定 |
| 反轉 | dolly_zoom | split_screen_3（8 秒） | 同段只放一個 |
| 高潮 | bullet_time（需後製確認凍結） | yoyo_zoom | 最大衝擊鏡鎖死機位 |
| 收尾 | aerial_pullback | 極慢後拉 | 後拉會揭露未定義背景，先寫進場景 |

## 類型
| 類型 | 首選 | 禁用 |
|---|---|---|
| 對白 | 固定 CU／MCU | 所有強運鏡 |
| 動作 | 前段運鏡、衝擊鏡鎖死（對比成立） | 手持假動 |
| 仙俠 | bullet_time（身份優先、明寫髮長） | 服裝描述壓過參考臉 |
| 懸疑 | 緩推、dutch_canted | 連續同運鏡 |
| 日常 | 固定、緩推 | 強運鏡 |

## 驗證狀態與降級
- pass：dutch_canted、top_down_rise、high_angle_tilt_down、bullet_time、dolly_zoom（正反向）、snorricam、eyes_in、aerial_pullback、super_dolly_in、yoyo_zoom、split_screen_3、ots_reveal。
- 未實測：緩推、後退跟拍、後拉、震屏；handheld 家機實測無效，不要用。
- 不在 preset 內的運鏡：以 `move_preset` 留空、`mv` 手寫，lint 只給提示。

## 基礎與進階運鏡速查（PR-15a，參考 https://24frames.art/ 的判斷後以自己的話改寫；網站自稱模板未真機驗證，以下全為「未實測」）
preset 於 15b 補上；在那之前這些運鏡以 `mv` 手寫，lint 只給提示。秒數只用 5／8／10／15。

| 運鏡 | 何時用 | 翻車點 | 幅度與秒數建議 |
|---|---|---|---|
| push_in 推（dolly in） | 收緊情緒、看一個細節、從環境走進人物 | 只寫 zoom in 會變變焦放大、畫面扁平；太快像要撞上；臉漂移 | 景別降一級（中景→近景），5–8 秒慢推 |
| pull_back 拉（dolly out） | 段落收尾、揭示孤立或被包圍 | 被做成變焦縮小、背景壓平；中途主體被前景遮住 | 景別升一級，先把背景寫進場景 |
| pan 搖 | 同空間兩個對象、跟橫移目標、懸念 | 太快出果凍；被做成整機橫移；結尾不停穩 | 原地轉 30–60°，落點寫明並停穩 |
| truck 橫移 | 一排並列物（書架、街景） | 與跟拍混淆；軌跡歪；速度忽快忽慢 | 直線勻速，寫起點與終點物件 |
| follow 跟拍 | 行走對話、追逐、帶觀眾進空間 | 主體越跑越小；腳飄；中途換臉換衣 | 主體在畫面比例不變；三主體以上降級 |
| crane_up／crane_down 升降 | 地面升到全景，或高處降下揭示 | 寫成拉升被當變焦；地平線傾斜；高度變化太小 | 至少升降一個人高以上，地平線保持水平 |
| low_angle 仰角 | 權力、英雄、威脅 | 仰角太大腿被拉長；再疊廣角失真 | 低機位 15–30° 仰，不疊廣角 |
| static_hold 固定 | 對峙、凝視、對白、衝擊鏡 | 模型自己偷偷動 | 明寫鏡頭全程不動 |
| orbit 環繞 | 立體感、英雄亮相 | 臉逐步變形換人（最常見）；不寫幅度原地抽搐；背景糊 | H3 寫成 truck＋pan，不用 orbit 字；弧度 ≤90° |
| rise_orbit 升起環繞 | 段落收尾、史詩全貌 | 兩種運動疊加最易崩；速度忽快忽慢 | 只在無對白、單主體的鏡用，8 秒以上 |
| steadicam 穩定跟走 | 走廊進房間、串連空間 | 中途換房間；門框牆角扭曲；人數換裝變 | 一個連續空間，不超過 10 秒 |
| macro_push 微距推 | 細節（水珠、紋理、咬合） | 焦點亂跑；紋理變無意義圖案；景深太淺 | 單一小物件，寫焦點落點 |
| rack_focus 轉焦 | 揭示後景的人、物轉人 | 前後都清晰看不出轉焦；機位也在動；轉太快像失焦 | 固定機位、淺景深，約 3 秒轉完 |
| aerial_reveal 升起揭示 | 片頭、地點交代、段尾釋放 | 一開始就露全貌；太快像穿越機；地形比例錯 | 從遮擋物後升起，越過瞬間才揭示 |
| whip_pan 甩鏡 | 轉場、喜劇節奏 | 整段全糊收不回；末幀仍漂；甩兩次 | 單次甩、末端急停在新對象，≤1 秒動作 |
| crash_zoom 急推 | 笑點、頓悟、港片強調 | 做成慢推；人臉扭曲；整段都急推 | 半秒內中景→臉部特寫，機位不動 |
| fpv 穿越機視角 | 開場鉤子、展示空間、速度 | 純糊；空間幾何錯亂；觀眾暈 | 只做穿過單一門洞或通道，≤8 秒 |
| pov 主觀視角 | 代入、驚嚇、第一人稱 | 變第三人稱；多出手或肢體；視線與身體矛盾 | 只露手或工具，不露臉 |
| foreground_wipe 前景遮擋 | 轉場、藏連戲錯、接不相干場景 | 遮擋物成一團；遮後跳變太硬；遮不徹底見接縫 | 用大面積實體（人背、牆、樹）完全遮滿畫面 |

### 新式併入情緒與節點
- 情緒：緊張→push_in／follow；孤立→pull_back／crane_up；驚訝頓悟→crash_zoom（喜劇、動作）；權力威脅→low_angle；懸念→pan 到未見物；沉浸→steadicam／pov。
- 節點：開場→aerial_reveal／crane_up；登場→low_angle／rack_focus；轉場→whip_pan／foreground_wipe；收尾→pull_back／rise_orbit；細節揭示→macro_push／rack_focus。
