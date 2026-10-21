"""`references/h3` 與上游 h3-video-prompting 的同步守門員。

背景：SKILL.md 曾寫「與上游同名同步」，實際落後 15 個檔案、還缺
`shot-five-part.md`——因為同步純靠人工、沒有任何紀錄或檢查。
現在 `references/h3/UPSTREAM.json` 記下「同步到哪個 commit、每個檔的 sha256」，
這支測試在 CI（無網路）就能擋住：

- 檔案被偷改（hash 不符）
- 檔案被刪（缺檔）
- 新增了未宣告的檔案（沒進 manifest、也不是 local_only）
- `shot-five-part.md` 這種上游新檔案再次漏掉

真正的「上游又有新 commit」由 `scripts/sync_h3_reference.py --check` 發現，
它需要本機 upstream clone，所以不進 CI。
"""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
H3 = ROOT / "references" / "h3"
MANIFEST_PATH = H3 / "UPSTREAM.json"


def sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


class H3ReferenceSyncTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.synced = self.manifest.get("files") or {}
        self.local_only = set(self.manifest.get("local_only") or [])

    def test_manifest_records_upstream_commit(self):
        commit = self.manifest.get("upstream_synced_commit") or ""
        self.assertRegex(commit, r"^[0-9a-f]{40}$",
                         "UPSTREAM.json 必須記下同步到的上游 commit（40 碼）")
        self.assertIn("h3-video-prompting", self.manifest.get("upstream_repo", ""))

    def test_every_synced_file_exists_and_matches_manifest(self):
        drifted, missing = [], []
        for name, digest in self.synced.items():
            path = H3 / name
            if not path.is_file():
                missing.append(name)
            elif sha256(path) != digest:
                drifted.append(name)
        self.assertEqual(missing, [], f"上游同步檔被刪：{missing}")
        self.assertEqual(drifted, [],
                         f"這些檔案與 UPSTREAM.json 不符（被改過或沒同步）：{drifted}\n"
                         "→ 跑 `python scripts/sync_h3_reference.py --check`，"
                         "必要時 `--sync --write-manifest`")

    def test_no_undeclared_files(self):
        declared = set(self.synced) | self.local_only
        actual = {p.name for p in H3.glob("*.md")}
        undeclared = sorted(actual - declared)
        self.assertEqual(undeclared, [],
                         f"references/h3 有未宣告的檔案：{undeclared}\n"
                         "→ 加進 UPSTREAM.json 的 files（上游檔）或 local_only（本專案追加）")
        stale_manifest = sorted(set(self.synced) - actual)
        self.assertEqual(stale_manifest, [], f"manifest 列了不存在的檔案：{stale_manifest}")

    def test_upstream_new_file_is_present(self):
        # 這次漂移的具體症狀：上游 2026-10-21 的 PR #4 加了 shot-five-part.md
        self.assertIn("shot-five-part.md", self.synced)
        self.assertTrue((H3 / "shot-five-part.md").is_file())

    def test_local_annotations_survived_sync(self):
        # scenarios-people.md 有三處本專案標註，sync 時靠 UPSTREAM.json 的 local_annotations 重套
        text = (H3 / "scenarios-people.md").read_text(encoding="utf-8")
        for marker in ("★漫劇主力", "★漫劇常用", "★漫劇旁白常用"):
            self.assertIn(marker, text, f"同步把本地標註吃掉了：{marker}")


if __name__ == "__main__":
    unittest.main()
