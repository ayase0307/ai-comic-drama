# 生物動態與階段寫法（ai-comic-drama 本地補充）

> 本檔只存在於本專案（不屬上游 h3-video-prompting）。內容來自噩盡島 EP02／EP03 的多輪抽卡紀錄（D 系列、R3-2／3／20／22／23／31）。
> 標「已驗」＝在家機 H3 抽卡看過成功；標「單例」＝只有一個鏡頭成功，換構圖可能失效；標「推測」＝尚未驗證。

## 1. 先分「力學類別」，再選動態詞

通用句（如 `ringed body heaves and ripples`）用在不同生物會出錯：蛇段用蟲的蠕動詞，老大評為「非常不自然」。每個生物段先決定類別，只用該類別的詞。

| 類別 | 身體怎麼動 | 常用動詞骨架 | 不要混用 |
|---|---|---|---|
| snake 蛇／巨蟒 | 身體 S 形波浪向前，頭相對穩定，攻擊是頭頸彈出 | 頭穩住、身體 S 形波浪、頭頸蓄力後彈出撲咬、咬住後甩頭、尾巴大幅掃甩 | 蠕動、縮成肉環、環節起伏（蟲的詞） |
| worm 蟲 | 靠環節收縮，前端伸縮、後端跟上，沒有穩定的頭 | 前端探出、環節依序收縮鼓起、整條拱起再攤平、原地扭擺 | S 形游行、撲咬、吐信（蛇的詞） |
| quadruped 四足獸 | 四肢交替承重，脊柱隨步態起伏，頭頸反向平衡 | 前爪蹬地、後腿蓄力撲出、落地吸收、甩頭咬住拖行 | 無肢類的滑行 |
| bird 鳥／翼獸 | 翅膀揮幅主導，陸上步態短促，頭部啄擊 | 翅膀全展拍擊、俯衝收翅、落地收翅小跳、頭頸前啄 | 滑行不收翅 |

## 2. 狀態動態（四類都要有，缺哪一段模型就畫成不動的道具）

- 常態：每個在鏡內的生物都要有自己的持續動作；只寫主角動作，生物會變成「死掉的道具」（D19）。block 句要用動詞，`lies on the ground` 會讓生物定格，改 `writhes and lashes on the ground`（D28）。
- 受擊反應：先寫「是哪個部位被打」，再寫生物的反應與接下來的動作（因果）。蛇：受擊後身體彈開、顎張開、劇烈翻滾，之後再接下一拍。受擊反應詞要含 recoils／dust／debris 之類的反饋詞，編譯器 E16 才認得（R3-11 已擴充詞表）。
- 咬住後：被咬住的人與生物頭要分開寫誰在動。局部接觸（咬、刺）時，生物外觀只露頭頸，避免把整條蛇寫進去（模型會為了擺全身拉成遠景，R3-31）。
- 被拉尾：寫次數與位移量，如 `yanks backward twice and he slides back half a body length, fingers scraping streaks`；`drags him back` 這種籠統句不會發生（R3-20）。
- 垂死：寫逐步失力（抽搐 → 變慢 → 整條攤開 → 末端還有一次輕顫），不要只寫終態形容詞；大招傷害也要寫成「命中當下分解的事件」（皮一條條撕開、焦黑冒煙），終態形容詞（torn open）常讓生物保持完好（R3-20）。
- 尾巴非主角時，用比喻加粗細：`握處不比手腕粗，離手那段像鬆開的消防水帶上下大浪甩`，並寫明顏色（單例：尾巴是主體的 MS 側面只做到下垂成弧線，D35）。

## 3. 階段與型態（對應編譯器 variants.on_screen_en／banned_en）

同一生物不同階段（蟲 → 膨脹 → 蛇 → 殘骸）要各有：參考圖、當階段的外觀句、前一型態的禁用詞。

```json
"variants": {
  "worm":  { "on_screen_en": "a finger-thick blind worm; one head end, the tail tapers and has no mouth",
             "banned_en": ["serpent", "fangs", "hood"] },
  "snake": { "on_screen_en": "a huge snake as thick as a car tire, one head, a long tapering tail",
             "banned_en": ["earthworm", "round mouth", "fleshy folds", "squirm"] }
}
```

- bible 的 `characters[].variants.<階段>` 或 stage5 綁定裡該階段的 `creatures[]` 條目都可寫 `on_screen_en`、`banned_en`（陣列或逗號分隔字串）。編譯器只在該階段的鏡頭寫一句 `In this shot the creature is: …`，並在該鏡文字含禁用詞時給警告（R3-2，只警告不中止；沒寫這兩個欄位時行為不變）。
- 外觀句用可見幾何與比例，不用形容詞堆疊：`no thicker than a finger and shorter than the sneaker's toe cap, a blind rounded tip with no eyes and no face`（R3-23，已驗）。
- 早期型態的「無眼」要明寫，而且共用的生物定義句若帶 `two small eyes`，正向句蓋不過它（D36）；所以階段外觀句才逐鏡放，不要放進全段共用的 Subject 定義。
- 有蛇參考圖或蛇詞庫的集裡，小蟲段與膨脹段也會長出眼睛與嘴；每一階段都要用該階段專屬參考圖（#60、R3-23）。

## 4. 纏繞與穿刺（已知會畫壞，先避開）

- 水平腰圈無論寫 belt／thin rear part／topology 都會變游泳圈（D25、D33、D34）。改用上身斜勒或「沉重圍巾壓在頸根與鎖骨，從腋下消失到背後」，被纏者雙手各給任務（一手推蛇頭、一手握筆），明寫 `neither hand ever touches the body`（R3-22，單例）。
- 規劃時先做長度預算：纏圈數 × 周長 + 頭頸 + 可拉的尾長 ≤ 全長，否則模型會畫出兩頭或兩截（#178）。
- 道具貫穿生物：寫「可見結果」而非動作或比喻，如 `the lower half of the spear is hidden inside the head, only the upper shaft stands straight out of the crown, and the pinned head does not move`（D18，已驗）。
- 畫外的人不要寫 `beyond the edge of frame`，模型會把人畫到邊緣（R4-9）。

## 5. 使用順序

1. 階段 4 寫分鏡前，決定每段的生物類別與階段，填進 bible variants。
2. 逐鏡只放該類別的動態詞，並安排常態、受擊、受擊後三種狀態至少各一鏡。
3. 編譯後看 `compile_notes` 有沒有 R3-2 警告，再看 E16、creature_lint 的警告。
4. 抽卡後逐幀驗：型態是否與階段一致、頭口眼數是否正確（`h3d verdict`）。
