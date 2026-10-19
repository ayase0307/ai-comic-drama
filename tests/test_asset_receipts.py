import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_stage_review as review
import project_state as ps

class AssetReceiptTests(unittest.TestCase):
    def setUp(self):
        temp_root=Path(__file__).resolve().parents[1]/'tmp'
        temp_root.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=temp_root)
        self.p=Path(self.tmp.name)
        for d in ('adapt','assets','images/assets','review'):(self.p/d).mkdir(parents=True,exist_ok=True)
        (self.p/'assets.md').write_text('Asset bible',encoding='utf8')
        (self.p/'adapt/character-bible.md').write_text('Characters',encoding='utf8')
        (self.p/'adapt/bible.json').write_text(json.dumps({'characters':[{'character_id':'E-voice','entity_type':'voice'}],'locations':[]}),encoding='utf8')
        self.assets=[{'stable_id':'scene','display_name_zh':'場景','source_id':'L-scene','target_path':'images/assets/scene.png','required':True},
                     {'stable_id':'optional','display_name_zh':'可選','target_path':'images/optional.png','required':False}]
        (self.p/'assets/reference-manifest.json').write_text(json.dumps({'assets':self.assets}),encoding='utf8')
        Image.new('RGB',(16,9),'white').save(self.p/'images/assets/scene.png')

    def tearDown(self):self.tmp.cleanup()

    def test_manifest_review_displays_nested_asset_without_requesting_voice_or_optional_image(self):
        passed,errors,page=review.build_stage_2(self.p,ps.load_state(self.p))
        self.assertTrue(passed,errors)
        self.assertIn('images/assets/scene.png',page)
        self.assertNotIn('images/E-voice.png',page)

    def test_missing_required_manifest_image_blocks_review(self):
        (self.p/'images/assets/scene.png').unlink()
        passed,errors,_=review.build_stage_2(self.p,ps.load_state(self.p))
        self.assertFalse(passed)
        self.assertTrue(any('scene.png' in e for e in errors))

    def test_stage2_snapshot_binds_nested_images_and_manifest(self):
        before=ps.stage_snapshot(self.p,2)
        paths={a['path'] for a in before['artifacts']}
        self.assertIn('images/assets/scene.png',paths)
        self.assertIn('assets/reference-manifest.json',paths)
        Image.new('RGB',(16,9),'black').save(self.p/'images/assets/scene.png')
        self.assertNotEqual(ps.snapshot_fingerprint(before),ps.snapshot_fingerprint(ps.stage_snapshot(self.p,2)))

if __name__=='__main__':unittest.main()
