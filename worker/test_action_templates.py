import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from run_job import load_spec, write_workspace, collect_artifacts


class ActionTemplateTests(unittest.TestCase):
    def test_deferred_matte_never_labels_raw_or_keyed_frames_as_game_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'run'; cell=run/'actions/slash/right'
            (cell/'raw/frames').mkdir(parents=True)
            (cell/'raw/output.mp4').write_bytes(b'video fixture')
            (cell/'raw/frames/000000.png').write_bytes(b'original RGB')
            rgba=cell/'processing/0001/frames/rgba'; rgba.mkdir(parents=True)
            (rgba/'000000.png').write_bytes(b'unapproved distance key')
            out=Path(tmp)/'out'
            collect_artifacts(out,{'action':'slash','facing':'right','matte_profile':'deferred'},run,cell)
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['raw_frame_count'],1)
            self.assertIsNone(manifest['all_frames_dir'])
            self.assertEqual(manifest['all_frame_count'],0)
            self.assertEqual(manifest['matte_status'],'pending_external_processing')
            self.assertFalse((out/'frames/all').exists())
            self.assertEqual((out/'frames/raw/000000.png').read_bytes(),b'original RGB')

    def test_preview_pack_failure_preserves_full_video_and_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            run=Path(tmp)/'run'; cell=run/'actions/run/right'
            (cell/'raw').mkdir(parents=True)
            (cell/'raw/output.mp4').write_bytes(b'video fixture')
            rgba=cell/'processing/0001/frames/rgba'; rgba.mkdir(parents=True)
            (rgba/'000000.png').write_bytes(b'frame fixture')
            out=Path(tmp)/'out'
            collect_artifacts(out,{'action':'run','facing':'right'},run,cell,pack_warning='Preview cell too small')
            manifest=json.loads((out/'manifest.json').read_text())
            self.assertEqual(manifest['all_frame_count'],1)
            self.assertIsNone(manifest['sheet'])
            self.assertEqual(manifest['warnings'],['Preview cell too small'])
            self.assertEqual((out/'frames/all/000000.png').read_bytes(),b'frame fixture')

    def make_template(self, root, action, facing='right'):
        root.joinpath('source.png').write_bytes(b'fixture; workspace only copies source')
        root.joinpath('spec.json').write_text(json.dumps({'action':action,'facing':facing}))
        spec=load_spec(root)
        write_workspace(root,spec)
        template=tomllib.loads((root/'workspace/templates/job/template.toml').read_text())
        return spec,template

    def test_motion_constraints_match_action(self):
        for action,expected in [('idle','static'),('parry','static'),('run','locomotion'),('walk','locomotion'),('jump','displacement'),('dash','displacement'),('slash','displacement'),('hurt','displacement'),('turn','displacement')]:
            with self.subTest(action=action),tempfile.TemporaryDirectory() as tmp:
                _,template=self.make_template(Path(tmp),action)
                self.assertEqual(template['actions'][0]['motion_class'],expected)

    def test_documented_side_alias_reaches_supported_upstream_facing(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec,_=self.make_template(Path(tmp),'run','side')
            self.assertEqual(spec['facing'],'right')
            self.assertTrue((Path(tmp)/'workspace/projects/job/sprite/sources/right.png').exists())

    def test_motion_text_and_registration_survive_template_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            spec={'name':'hero','action':'run','facing':'right','width':640,'height':640,'motion':'At 0.5 seconds the left foot passes the right.'}
            (root/'spec.json').write_text(json.dumps(spec))
            (root/'source.png').write_bytes(b'fixture')
            write_workspace(root,load_spec(root))
            template=tomllib.loads((root/'workspace/templates/job/template.toml').read_text())
            self.assertEqual(template['canvas']['baseline_ratio'],.856)
            self.assertEqual((root/'workspace/templates/job/motions/run.txt').read_text().strip(),spec['motion'])


if __name__=='__main__':unittest.main()
