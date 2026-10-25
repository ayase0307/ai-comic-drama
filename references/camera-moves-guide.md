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
