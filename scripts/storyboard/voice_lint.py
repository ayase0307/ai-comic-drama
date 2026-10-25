#!/usr/bin/env python3
"""畫外音／旁白的確定性 lint（PR-10c，findings #104 #114 #122 #123）。

只讀提示詞文字，不改任何東西；被 audit_refs_and_segments 與 project_state 匯入，
所以這裡不得替換 sys.stdout／sys.stderr（Windows CI 規則）。

- E43：一鏡寫了說話動詞（says／speaks／narrates／the line is heard…）卻沒有 <d> 逐字台詞。
  H3 看到「有人在說話」卻沒拿到字，會自編亂語或念出不相干的聲音（#122；噩盡島
  stage6/audio-audit.md 實測）。外部化的句子就不要在提示詞裡提「誰在說」；要 H3 念就給 <d>。
- E44：畫外句（O.S.／V.O.）同鏡的表情／動作寫了張嘴、喘氣、嘴唇分開。H3 會讓露臉者跟著開口，
  看起來像他在說那句畫外台詞（#123）。改成 lips pressed tightly shut。

嚴重度：預設只回警告；strict=True（h3d next、新核准、自動核准）才算錯誤。
已核准階段的重新驗證不走 strict，舊專案不因新檢查整批失去核准。
"""
from __future__ import annotations

import re
from typing import Dict, List

SHOT_SPLIT = re.compile(r"(?=\[Shot \d+\])")
D_BLOCK = re.compile(r"<d>.*?</d>", re.S)
# 說話動詞：要有「發聲的人」當主詞（he／she／<Subject N>／(Sn)／voice／narrator／人物名詞），
# 「the stance says everything」「the notice speaks in a calm hand」這類修辭不算。
_SPEAK_VERB = r"(?:says|speaks|is speaking|narrates|asks|replies|answers|mutters|murmurs|whispers|calls out|shouts)"
_SPEAKER_SUBJ = (
    r"(?:\b(?:he|she|they|someone|somebody|voice|narrator|man|woman|boy|girl|guide|teacher|watchman|"
    r"driver|doctor|nurse|elder|monk|master|disciple|student|stranger|guard|bird|creature|beast)\b|"
    r"<Subject \d+>|\(S\d+\))"
)
SPEAK_RE = re.compile(
    rf"{_SPEAKER_SUBJ}(?:\s+[\w'-]+){{0,2}}?\s+{_SPEAK_VERB}\b|"
    r"\b(?:the )?line is heard\b|\bis heard saying\b|\bas if speaking\b|"
    r"\b(?:off-screen|offscreen) (?:voiceover|voice-over|narration)\b|\b(?:speaks|narrates) off-screen\b",
    re.IGNORECASE,
)
# 否定與固定句：不算「有人在說話」。
NEGATED_SPEAK_RE = re.compile(
    r"\b(?:without|not|never|no one|nobody|stops?|stopped|doesn't|does not|don't|do not|isn't|is not|"
    r"before|instead of)\s+(?:\w+\s+){0,2}?(?:says|speaks|speaking|narrates|narrating|asks|replies)\b|"
    r"\b(?:says|speaks|asks) (?:nothing|no word|not a word)\b|\bis the visible speaking character\b",
    re.IGNORECASE,
)
OFFSCREEN_LINE_RE = re.compile(r"says in an off-screen voiceover|heard from [^<]{0,200}?off-screen", re.IGNORECASE)
MOUTH_OPEN_RE = re.compile(
    r"\b(?:mouths? (?:hangs? |falls? |drops? |is |are |half |slightly |wide )*open|open[- ]mouthed|"
    r"gasp(?:s|ing|ed)?|lips? (?:part|parts|parted|parting)|jaw (?:drops|dropping|hangs|falls) open)\b",
    re.IGNORECASE,
)


def _detail_body(prompt_text: str) -> str:
    m = re.search(r"detailed_description:(.*?)(?:\n\s*\n[a-z_]+:|\Z)", prompt_text or "", re.S)
    return m.group(1) if m else (prompt_text or "")


def _shot_tag(block: str) -> str:
    m = re.match(r"\[Shot (\d+)\]", block)
    return f"Shot {m.group(1)}" if m else "（段首）"


def voice_issues(prompt_text: str) -> List[Dict[str, str]]:
    """回傳 [{code, shot, message}]；不分嚴重度，呼叫端依 strict 決定算錯誤或警告。"""
    issues: List[Dict[str, str]] = []
    for block in SHOT_SPLIT.split(_detail_body(prompt_text)):
        if not block.strip().startswith("[Shot"):
            continue
        tag = _shot_tag(block)
        no_lines = D_BLOCK.sub(" ", block)
        if "<d>" not in block:
            cleaned = NEGATED_SPEAK_RE.sub(" ", no_lines)
            m = SPEAK_RE.search(cleaned)
            if m:
                issues.append({
                    "code": "E43",
                    "shot": tag,
                    "message": (
                        f"[E43: 有說話動詞卻沒給台詞] {tag} 寫了「{m.group(0)}」但這一鏡沒有 <d> 逐字台詞；"
                        f"H3 會自編亂語。要 H3 念就寫官方畫外句式加 <d>[Chinese] 台詞</d>，"
                        f"走外部 TTS 就刪掉說話句、只留嘴閉合與環境音（#122）。"
                    ),
                })
        elif OFFSCREEN_LINE_RE.search(block) and "lips remain completely closed" in block.lower():
            m = MOUTH_OPEN_RE.search(no_lines)
            if m and "no face is on screen" not in block.lower():
                issues.append({
                    "code": "E44",
                    "shot": tag,
                    "message": (
                        f"[E44: 畫外句同鏡張嘴] {tag} 是畫外句（嘴應閉合），表情／動作卻寫了「{m.group(0)}」；"
                        f"H3 會讓露臉者跟著開口，像他在說那句台詞。改成 lips pressed tightly shut（#123）。"
                    ),
                })
    return issues


def voice_lint(prompt_text: str, strict: bool = False) -> Dict[str, List[str]]:
    msgs = [i["message"] for i in voice_issues(prompt_text)]
    return {"errors": msgs if strict else [], "warnings": [] if strict else msgs}
