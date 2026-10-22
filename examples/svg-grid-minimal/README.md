# 最小範例：零設定 SVG 構圖

只有一個 Layer 2 段落（現代咖啡廳 6 鏡），沒有 `staging/`、沒有 cast，用來確認新專案什麼都不寫也能出構圖。

```bash
python scripts/h3d.py sketch --root examples/svg-grid-minimal --dry-run   # 先看會產生哪些檔
python scripts/h3d.py sketch --root examples/svg-grid-minimal --no-write-back
```

輸出：`panels/panel-NN-<shot_id>.png` 與 `images/grid-EP01-S02-a.png`（已加入 `.gitignore`）。

角色名字（林小雨、周澤）從 `continuity_anchors` 與單人鏡描述自動推得；兩人左右與朝向依「林小雨（畫左）、周澤（畫右）」換算。
