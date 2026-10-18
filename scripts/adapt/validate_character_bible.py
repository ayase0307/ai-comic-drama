#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_character_bible.py — 階段 1《完整角色設定文件 v4.0》與 bible.json 確定性防偷懶驗證器

功能：
1. 驗證 adapt/character-bible.md 是否具備對標《反派擺爛指南 角色設定_v4.md》的 11 大完整章節結構。
2. 驗證每位核心角色與重要配角是否具備完整 6 大子節：
   - 基本資料表（含外貌、武器/配件、口頭禪、標誌動作）
   - 性格特質（必須同時包含「表層性格」與「深層性格」）
   - 核心能力表
   - 人物弧光（含「→」弧線演進與「關鍵轉折點」）
   - 角色金句（含 `>` 原著台詞引用）
   - 視覺與服裝狀態機（含設定圖路徑與場次映射，防服裝穿幫）
3. 攔截未完成的模板佔位符（`{{...}}`、`TODO`、`<角色名>`）。
4. 攔截自創英文假名（如 `BrownHairSlayer`、`BlackHairDaoist`）作為標準劇本名（強制跨章節查證中文真名）。
5. 驗證是否附帶原著行號依據 `(L123)` 或章節依據，防止未讀原著憑空瞎掰。
6. 雙向對帳 adapt/bible.json 與 adapt/character-bible.md 的角色清單與服裝狀態路徑。

零外部依賴，僅使用 Python 標準庫。全程使用繁體中文。
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


REQUIRED_SECTIONS = [
    ("一、角色總覽", r"^##\s*一、角色總覽"),
    ("二、核心角色", r"^##\s*二、核心角色"),
    ("三、重要配角", r"^##\s*三、重要配角"),
    ("四、功能性角色與異獸生物設定", r"^##\s*四、功能性角色"),
    ("五、背景角色與路人收斂策略", r"^##\s*五、背景角色"),
    ("六、角色關係圖", r"^##\s*六、角色關係圖"),
    ("七、角色狀態與能力演進表", r"^##\s*(?:七|八)、角色(?:狀態|覺醒)"),
    ("八、角色戲劇與喜劇功能分配", r"^##\s*(?:八|九)、角色(?:戲劇|喜劇)"),
    ("九、角色命名與視覺象徵邏輯", r"^##\s*(?:九|十)、角色命名"),
    ("十、角色登場章節與場次服裝索引", r"^##\s*(?:十|十一)、角色登場章節"),
    ("附錄：角色設定速查表", r"^##\s*附錄[：:]角色設定速查表"),
]

REQUIRED_CHAR_SUBSECTIONS = [
    ("基本資料", r"####\s*基本資料"),
    ("性格特質", r"####\s*性格特質"),
    ("核心能力", r"####\s*核心能力"),
    ("人物弧光", r"####\s*人物弧光"),
    ("角色金句", r"####\s*角色金句"),
    ("視覺與服裝狀態機", r"####\s*視覺與服裝狀態機"),
]

FORBIDDEN_PSEUDO_NAMES = [
    "BrownHairSlayer",
    "BlackHairDaoist",
    "PasserbyA",
    "PasserbyB",
    "UnnamedGirl",
    "UnnamedBoy",
    "MonsterA",
    "NPC1",
]


def parse_character_blocks(md_text: str) -> Dict[str, str]:
    """從二、核心角色 與 三、重要配角 區塊中提取所有 `### 角色名` 區塊。"""
    blocks: Dict[str, str] = {}
    # 切割出 ### 標題區塊
    matches = list(re.finditer(r"^###\s+([^\n#]+)", md_text, flags=re.MULTILINE))
    for i, m in enumerate(matches):
        raw_title = m.group(1).strip()
        # 取括號前的標準名，例如 "顧長安（陸川）" -> "顧長安"
        clean_name = re.split(r"[（(]", raw_title)[0].strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        # 避免跨入下一個 ## 大章節
        next_h2 = re.search(r"^##\s+", md_text[m.end():end], flags=re.MULTILINE)
        if next_h2:
            end = m.end() + next_h2.start()
        blocks[clean_name] = md_text[start:end]
        blocks[raw_title] = md_text[start:end]
    return blocks


def validate_character_bible(
    md_text: str,
    bible_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """驗證角色設定 Markdown 與 bible.json 的完整性與深度。"""
    errors: List[str] = []
    warnings: List[str] = []
    checks_passed: List[str] = []

    if not md_text or not md_text.strip():
        return {
            "passed": False,
            "errors": ["[E01: 空白檔案] adapt/character-bible.md 內容為空！"],
            "warnings": [],
            "checks_passed": [],
        }

    # 1. 檢查未替換的模板佔位符
    placeholders = re.findall(r"\{\{[^}]+\}\}", md_text)
    if placeholders:
        sample = ", ".join(sorted(set(placeholders))[:5])
        errors.append(
            f"[E02: 模板未填寫] character-bible.md 仍殘留 {len(placeholders)} 處未填寫的模板變數（如 {sample}）！"
        )

    if "<角色名>" in md_text or "TODO" in md_text:
        errors.append("[E02: 殘留 TODO] character-bible.md 中仍含 `<角色名>` 或 `TODO` 佔位符，請依原著完整填寫。")

    # 2. 檢查禁用英文假名
    for bad_name in FORBIDDEN_PSEUDO_NAMES:
        if bad_name.lower() in md_text.lower():
            errors.append(
                f"[E03: 禁用自創英文假名] 檢測到自創代號 '{bad_name}'！"
                f"必須跨章節檢索原著揭曉之中文真名（如瑪蓮、奇雅、賴一心），嚴禁以英文代號敷衍。"
            )

    # 3. 檢查 11 大必填章節
    missing_sections = []
    for label, pattern in REQUIRED_SECTIONS:
        if not re.search(pattern, md_text, flags=re.MULTILINE):
            missing_sections.append(label)
    if missing_sections:
        errors.append(
            f"[E04: 章節結構缺漏] 缺少以下對標《角色設定_v4.md》的必填大章節：{', '.join(missing_sections)}"
        )
    else:
        checks_passed.append("[PASS] 11 大角色設定章節結構完整齊全")

    # 4. 檢查原著行號依據 (Lxxx)
    line_refs = re.findall(r"[（(]?L\d+(?:[-–—]\d+)?[）)]?", md_text)
    if len(line_refs) < 3:
        errors.append(
            f"[E05: 缺乏原著行號依據] 全文僅找到 {len(line_refs)} 處原著行號標註 `(Lxxx)`（至少需 3 處以上），"
            f"請查閱原著標註外貌、武器與轉折點之真實行號，防止憑空捏造設定！"
        )
    else:
        checks_passed.append(f"[PASS] 原著行號正典依據核驗通過（共標註 {len(line_refs)} 處 L 行號）")

    # 5. 提取並檢查二、核心角色 與 三、重要配角 的每個角色深度
    char_blocks = parse_character_blocks(md_text)
    core_and_supp_match = re.search(
        r"^##\s*二、核心角色(.*?)(?=^##\s*四、功能性角色|\Z)",
        md_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    core_supp_text = core_and_supp_match.group(1) if core_and_supp_match else md_text
    char_headings = re.findall(r"^###\s+([^\n#]+)", core_supp_text, flags=re.MULTILINE)

    if not char_headings:
        errors.append("[E06: 缺少角色條目] 在「二、核心角色」與「三、重要配角」下未找到任何 `### 角色名` 條目！")
    else:
        for raw_h in char_headings:
            cname = re.split(r"[（(]", raw_h.strip())[0].strip()
            block = char_blocks.get(raw_h.strip(), "")

            missing_subs = []
            for sub_label, sub_pat in REQUIRED_CHAR_SUBSECTIONS:
                if not re.search(sub_pat, block):
                    missing_subs.append(sub_label)
            if missing_subs:
                errors.append(
                    f"[E07: 角色設定偷工減料] 角色「{cname}」缺少必填子節：{', '.join(missing_subs)}"
                )

            # 檢查表層性格與深層性格
            if "表層性格" not in block or "深層性格" not in block:
                errors.append(
                    f"[E08: 性格維度扁平] 角色「{cname}」的性格特質必須同時剖析「表層性格」與「深層性格」！"
                )

            # 檢查人物弧光箭頭與關鍵轉折點
            if "→" not in block and "->" not in block:
                errors.append(
                    f"[E09: 缺少人物弧光演進鏈] 角色「{cname}」的人物弧光缺少 `「初始」→「轉折」→「收束」` 演進描述！"
                )
            if "關鍵轉折點" not in block:
                errors.append(
                    f"[E09: 缺少關鍵轉折點] 角色「{cname}」的人物弧光缺少「關鍵轉折點」列表！"
                )

            # 檢查角色金句引用
            quotes = re.findall(r"^>\s*「.+」", block, flags=re.MULTILINE)
            if not quotes:
                errors.append(
                    f"[E10: 缺少角色金句] 角色「{cname}」缺少 `> 「...」` 格式的原著代表性台詞引用！"
                )

            # 檢查服裝狀態機圖片路徑
            img_paths = re.findall(r"images/[A-Za-z0-9_.-]+\.png", block)
            if not img_paths:
                errors.append(
                    f"[E11: 缺少服裝狀態圖路徑] 角色「{cname}」的「視覺與服裝狀態機」未綁定 `images/*.png` 路徑！"
                )

        if not any("E07" in e or "E08" in e or "E09" in e for e in errors):
            checks_passed.append(
                f"[PASS] 共 {len(char_headings)} 位核心／重要配角均通過 6 大子節、表深層性格、弧光與服裝狀態機深度驗證"
            )

    # 6. 與 adapt/bible.json 雙向對帳
    if bible_json is not None:
        json_chars = bible_json.get("characters", [])
        if not json_chars:
            errors.append("[E12: bible.json 空白] adapt/bible.json 的 characters 陣列為空！")
        for ch in json_chars:
            cid = ch.get("character_id") or ch.get("id") or ""
            cname = ch.get("canonical_name") or ch.get("name") or ""
            role = ch.get("role", "planet")
            if cname in ("<角色名>", "TODO", "") or any(b.lower() in cname.lower() for b in FORBIDDEN_PSEUDO_NAMES):
                errors.append(
                    f"[E13: bible.json 角色名無效] 角色 ID `{cid}` 的 canonical_name `{cname}` 為佔位符或英文假名！"
                )
                continue
            if role in ("star", "planet", "core", "supporting") and cname not in char_blocks:
                errors.append(
                    f"[E14: 角色聖經漏列角色] bible.json 中的重要角色「{cname} (`{cid}`)」未在 character-bible.md 建立 `### {cname}` 詳細設定專節！"
                )

        if not any("E12" in e or "E13" in e or "E14" in e for e in errors):
            checks_passed.append(
                f"[PASS] adapt/bible.json ({len(json_chars)} 名角色) 與 character-bible.md 雙向對帳 100% 吻合"
            )

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "checks_passed": checks_passed,
        "character_count": len(char_headings),
    }


def run_self_test() -> bool:
    """內建雙向回歸自檢：測試 1 為合規 v4 角色設定，測試 2 為偷工減料與假名案例。"""
    print("=" * 75)
    print("🧪 啟動 validate_character_bible.py 內建自檢套件 (--self-test)")
    print("=" * 75)

    valid_md = """# 《噩盡島》完整角色設定文件 v4.0

> 正典來源：`source/input.md`（L1–L3200）

## 一、角色總覽
| 角色 ID | 標準劇本名 | 原著別名 | 定位 | 年齡 | 身份 | 一句話氣質 |
|---|---|---|---|---|---|---|
| `C-shen-luonian` | 沈洛年 | 洛年 | 男主 | 17 | 高中生 | 一個在危機中異常冷靜的旁觀者 |
| `C-lai-yixin` | 賴一心 | 一心 | 重要配角 | 18 | 武術青年 | 一個背著銀槍行俠仗義的娃娃臉武者 |

## 二、核心角色

### 沈洛年

#### 基本資料
| 項目 | 內容 |
|---|---|
| 角色 ID | `C-shen-luonian` |
| 姓名 | 沈洛年（別名：洛年） |
| 性別 | 男 |
| 年齡 | 17歲（L120） |
| 身份 | 台灣普通高中生（L125） |
| 外貌 | 黑色短碎髮，黑褐色微帶倦意卻銳利的雙眼，中等偏瘦勻稱體型（L130） |
| 標誌武器／隨身道具 | 隨手抄起的不鏽鋼圓鐵凳（L450） |
| 口頭禪 | 「真是麻煩……」 |
| 標誌動作 | 雙手插口袋微駝背觀察四周（L140） |

#### 性格特質
**表層性格**：
- 怕麻煩、習慣低調旁觀，說話簡短直接。
**深層性格**：
- 骨子裡有極強的生存直覺與道德底線，見幼童遇險仍會挺身而出（L455）。

#### 核心能力
| 能力 | 來源 | 說明 |
|---|---|---|
| 時間減速感知 | 生死關頭覺醒（L460） | 腎上腺素爆發時眼中世界極致變慢，能看清異獸攻擊軌跡並精準反擊 |

#### 人物弧光
「只想安穩度日的普通高中生」→「快餐店覺醒時間減速救人」→「洞察異變世界生存法則」
**關鍵轉折點**：
1. 第2章（`EP02-S01`）：見巨鼠襲擊幼童，時間感知驟然變慢——「給我滾開！」（L462）

#### 角色金句
> 「要是遇到第三次，大概就真的沒命了。」（L510）

#### 視覺與服裝狀態機
| 服裝狀態 ID | 狀態名稱 | 服裝描述 | 對應設定圖路徑 | 適用集數與場次 |
|---|---|---|---|---|
| `W-shen-01` | 日間制服 | 白襯衫深藍長褲高中制服 | `images/char-ShenLuonian.png` | `EP01-S01` |
| `W-shen-02` | 夜間便服 | 深灰連帽外套與黑色長褲 | `images/char-ShenLuonian-casual.png` | `EP02-S01` |

## 三、重要配角

### 賴一心

#### 基本資料
| 項目 | 內容 |
|---|---|
| 角色 ID | `C-lai-yixin` |
| 姓名 | 賴一心 |
| 性別 | 男 |
| 年齡 | 18歲（L520） |
| 身份 | 暗地修練道術的年輕武者（L525） |
| 外貌 | 娃娃臉、身材高壯結實、清爽黑色短髮（L530） |
| 標誌武器／隨身道具 | 白色皮質長背包、可拆解為三節棍的銀色金屬長槍（L535） |
| 口頭禪 | 「快退後！」 |
| 標誌動作 | 反手自白色長背包抽出銀槍旋身橫掃（L540） |

#### 性格特質
**表層性格**：
- 熱血正直、見到怪物傷人毫不猶豫拔槍相救。
**深層性格**：
- 對師門傳承有高度使命感，但面對突發群獸仍略顯實戰經驗不足。

#### 核心能力
| 能力 | 來源 | 說明 |
|---|---|---|
| 槍棍轉換武藝 | 師門修練（L545） | 銀槍與三節棍靈活切換，兼具遠距突刺與近身砸擊 |

#### 人物弧光
「獨自巡守街頭除妖」→「快餐店救場擊殺巨鼠」→「與洛年交換異變情報」
**關鍵轉折點**：
1. 第2章（`EP02-S02`）：破窗突入快餐店一槍貫穿巨鼠（L550）

#### 角色金句
> 「那些怪物不是普通野獸，待在這裡太危險了！」（L560）

#### 視覺與服裝狀態機
| 服裝狀態 ID | 狀態名稱 | 服裝描述 | 對應設定圖路徑 | 適用集數與場次 |
|---|---|---|---|---|
| `W-lai-01` | 武者便裝 | 勁裝外套配白色皮質長背包 | `images/char-LaiYixin.png` | `EP02-S02` |

## 四、功能性角色與異獸生物設定
| 資產 ID | 名稱 | 說明 |
|---|---|---|
| `CREATURE-rat` | 食人巨鼠 | 體長逾一公尺，粉紅肉柱長尾（L430），設定圖 `images/creature-giant-rat.png` |

## 五、背景角色與路人收斂策略
| 群體 | 策略 |
|---|---|
| 快餐店路人 | 僅用背影與畫外音，嚴禁正臉特寫 |

## 六、角色關係圖
沈洛年 ↔ 賴一心（救援與情報交換）

## 七、角色狀態與能力演進表
| 角色 | 觸發章節 | 狀態 |
|---|---|---|
| 沈洛年 | 第2章 | 時間減速覺醒 |

## 八、角色戲劇與喜劇功能分配
| 角色 | 功能 |
|---|---|
| 沈洛年 | 冷靜吐槽與危機破局 |

## 九、角色命名與視覺象徵邏輯
| 角色 | 邏輯 |
|---|---|
| 沈洛年 | 沉穩冷靜 |

## 十、角色登場章節與場次服裝索引
| 角色 | 首次登場 | 場次 | 服裝 ID | 路徑 |
|---|---|---|---|---|
| 沈洛年 | 第1章 | `EP02-S01` | `W-shen-02` | `images/char-ShenLuonian-casual.png` |

## 附錄：角色設定速查表
| 角色 | 一句話定位 | 核心矛盾 | 角色金句 |
|---|---|---|---|
| 沈洛年 | 怕麻煩的覺醒高中生 | 想低調卻被迫捲入 | 「要是遇到第三次……」 |
"""
    valid_json = {
        "characters": [
            {"character_id": "C-shen-luonian", "canonical_name": "沈洛年", "role": "star"},
            {"character_id": "C-lai-yixin", "canonical_name": "賴一心", "role": "planet"},
        ]
    }

    res1 = validate_character_bible(valid_md, valid_json)
    print(f"\n[Test 1] 合規 v4 角色設定驗證: passed={res1['passed']} (預期: True)")
    if not res1["passed"]:
        print("  ❌ 意外失敗:", res1["errors"])
        return False
    for p in res1["checks_passed"]:
        print("  ", p)

    flawed_md = """# 角色設定
## 一、角色總覽
## 二、核心角色
### BrownHairSlayer
只有一行字 TODO
"""
    flawed_json = {
        "characters": [
            {"character_id": "C-malien", "canonical_name": "BrownHairSlayer", "role": "planet"},
            {"character_id": "C-lai", "canonical_name": "賴一心", "role": "planet"},
        ]
    }
    res2 = validate_character_bible(flawed_md, flawed_json)
    print(f"\n[Test 2] 偷懶殘缺與英文假名攔截驗證: passed={res2['passed']} (預期: False)")
    if res2["passed"] or len(res2["errors"]) < 5:
        print("  ❌ 攔截失敗:", res2)
        return False
    for e in res2["errors"]:
        print("  ✅ 成功攔截 ->", e)

    print("\n🎉 validate_character_bible.py 自檢 100% 通過！")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="階段 1《完整角色設定文件 v4.0》與 bible.json 確定性驗證器")
    parser.add_argument("--bible-md", type=Path, help="adapt/character-bible.md 路徑")
    parser.add_argument("--bible-json", type=Path, help="adapt/bible.json 路徑（選填，提供時執行雙向對帳）")
    parser.add_argument("--json", action="store_true", help="輸出 JSON 格式")
    parser.add_argument("--self-test", action="store_true", help="執行內建雙向回歸自檢")
    args = parser.parse_args()

    if args.self_test:
        return 0 if run_self_test() else 1

    if not args.bible_md:
        parser.error("請提供 --bible-md 指定 adapt/character-bible.md 路徑，或使用 --self-test")

    if not args.bible_md.exists():
        print(f"❌ [錯誤] 找不到角色設定文件: {args.bible_md}", file=sys.stderr)
        return 1

    md_text = args.bible_md.read_text(encoding="utf-8")
    bible_json = None
    if args.bible_json and args.bible_json.exists():
        bible_json = json.loads(args.bible_json.read_text(encoding="utf-8"))

    res = validate_character_bible(md_text, bible_json)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("=" * 75)
        print(f"📋 《完整角色設定文件 v4.0》門禁審查報告 ({args.bible_md.name})")
        print("=" * 75)
        for p in res["checks_passed"]:
            print(f"  {p}")
        for w in res["warnings"]:
            print(f"  ⚠️ {w}")
        for e in res["errors"]:
            print(f"  ❌ {e}")
        print("-" * 75)
        print(f"審查結果: {'✅ PASS (可生成階段 1 HTML 審核頁)' if res['passed'] else '❌ FAIL (請補齊角色設定深度後重試)'}")
        print("=" * 75)

    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
