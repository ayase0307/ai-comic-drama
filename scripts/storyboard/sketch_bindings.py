#!/usr/bin/env python3
"""重建 Layer 2 時保留既有鏡頭的構圖綁定欄位（只用標準庫）。

構圖綁定（`codex_storyboard_panels.py` 或專案自己的綁定腳本寫回的欄位）：
  sketch_file、sketch_sha256、sketch_status、sketch_prompt、sketch_generation、sketch_qc

重建 layer2（例如 `handoff_to_skeleton.py --force`）會整份覆寫，這些欄位跟著消失，之後得手動重綁。
`carry_over(old, new, roots)` 以 shot_id 對應新舊鏡頭：舊鏡有 sketch_file、檔案還在、
目前檔案的 sha256 與 sketch_sha256 相符才把整組欄位搬到新鏡；不相符（圖被換掉、檔案不見、
沒記 sha256）一律不搬，讓 stage-4 照常要求重綁／重審。不產生任何新圖、不改其他欄位。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

BINDING_FIELDS = ("sketch_file", "sketch_sha256", "sketch_status", "sketch_prompt", "sketch_generation", "sketch_qc")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(sketch_file: str, roots: Iterable[Path]) -> Optional[Path]:
    p = Path(sketch_file)
    if p.is_absolute():
        return p if p.is_file() else None
    for root in roots:
        cand = Path(root) / p
        if cand.is_file():
            return cand
    return None


def _shots(seg: Any) -> List[Dict[str, Any]]:
    if not isinstance(seg, dict):
        return []
    return [s for s in seg.get("shots") or [] if isinstance(s, dict)]


def carry_over(old_seg: Any, new_seg: Any, roots: Iterable[Path]) -> Dict[str, List]:
    """把 old_seg 裡仍有效的構圖綁定搬到 new_seg（就地修改）。

    回傳 {"kept": [shot_id…], "dropped": [(shot_id, 原因)…]}；只看兩邊都有的 shot_id。"""
    roots = [Path(r) for r in roots]
    old_by_id = {str(s.get("shot_id")): s for s in _shots(old_seg) if s.get("shot_id")}
    kept: List[str] = []
    dropped: List[Tuple[str, str]] = []
    for shot in _shots(new_seg):
        sid = str(shot.get("shot_id") or "")
        old = old_by_id.get(sid)
        if not sid or not old or not old.get("sketch_file"):
            continue
        path = _resolve(str(old["sketch_file"]), roots)
        if path is None:
            dropped.append((sid, f"構圖檔不存在：{old['sketch_file']}"))
            continue
        want = str(old.get("sketch_sha256") or "").lower()
        if not want:
            dropped.append((sid, "舊綁定沒有 sketch_sha256，無法確認是同一張圖"))
            continue
        if _sha256(path) != want:
            dropped.append((sid, f"構圖檔 sha256 已變：{old['sketch_file']}"))
            continue
        for key in BINDING_FIELDS:
            if key in old:
                shot[key] = old[key]
        kept.append(sid)
    return {"kept": kept, "dropped": dropped}
