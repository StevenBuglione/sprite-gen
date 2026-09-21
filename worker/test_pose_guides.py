import copy
import unittest
from pose_guides import add_guides, GuidedTemplate
from types import SimpleNamespace

class PoseGuideTests(unittest.TestCase):
    def test_adapter_preserves_upstream_template_introspection(self):
        template=SimpleNamespace(source_sha256='source',graph={'node':{}},binding_spec={'bindings':{}})
        wrapped=GuidedTemplate(template,None,None)
        self.assertIs(wrapped.graph,template.graph)
        self.assertIs(wrapped.binding_spec,template.binding_spec)

    def setUp(self):
        self.graph = {
            'source':{'class_type':'MiniMaxH3ImageToVideo','inputs':{'length':39,'vae':['vae',0],'last_frame':['last',0]}},
            'guider':{'class_type':'BasicGuider','inputs':{'conditioning':['source',0]}},
            'sampler':{'class_type':'SamplerCustomAdvanced','inputs':{'latent_image':['source',1]}},
            'vae':{'class_type':'VAELoader','inputs':{}},
        }

    def test_all_pose_anchors_reach_guider_without_changing_latent_or_template(self):
        original = copy.deepcopy(self.graph)
        guides = [{'frame':f,'uploaded':f'pose-{f}.png'} for f in (9,19,28)]
        graph = add_guides(self.graph,guides)
        self.assertEqual(self.graph,original)
        self.assertEqual(graph['guider']['inputs']['conditioning'],['sprite_guide_2',0])
        self.assertEqual(graph['sampler']['inputs']['latent_image'],['source',1])
        for i, frame in enumerate((9,19,28)):
            node = graph[f'sprite_guide_{i}']['inputs']
            self.assertEqual(node['frame_idx'],frame)
            self.assertEqual(node['positive'],['source',0] if i==0 else [f'sprite_guide_{i-1}',0])
            self.assertEqual(node['latent'],['source',1])

    def test_invalid_guides_cannot_silently_replace_first_last_or_overlap(self):
        for frames in ((0,),(38,),(39,),(-1,),(9,9)):
            with self.subTest(frames=frames), self.assertRaises(ValueError):
                add_guides(self.graph,[{'frame':f,'uploaded':'x.png'} for f in frames])

if __name__=='__main__': unittest.main()
