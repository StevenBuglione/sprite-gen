"""Job-scoped H3 keyframe conditioning; preserve the submitted graph and hashes."""
import base64
import copy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path


def add_guides(graph, guides):
    result = copy.deepcopy(graph)
    sources = [key for key, node in result.items() if node['class_type'] == 'MiniMaxH3ImageToVideo']
    if len(sources) != 1:
        raise ValueError('Pose guides require exactly one H3 image-to-video node')
    source = sources[0]
    original = [source, 0]
    consumers = [(node, key) for node in result.values() for key, value in node.get('inputs', {}).items() if value == original]
    if not consumers: raise ValueError('H3 conditioning is not consumed')
    previous = original
    length = result[source]['inputs']['length']
    seen = set()
    for i, guide in enumerate(guides):
        frame = guide['frame']
        if frame <= 0 or frame >= length or frame in seen or (frame == length-1 and 'last_frame' in result[source]['inputs']):
            raise ValueError('Duplicate, anchored or out-of-range guide')
        seen.add(frame)
        image_id, guide_id = f'sprite_guide_image_{i}', f'sprite_guide_{i}'
        if image_id in result or guide_id in result: raise ValueError('Guide node collision')
        result[image_id] = {'class_type':'LoadImage','inputs':{'image':guide['uploaded']}}
        result[guide_id] = {'class_type':'MiniMaxH3AddGuide','inputs':{
            'positive':previous,'latent':[source,1],'frame_idx':frame,
            'vae':result[source]['inputs']['vae'],'image':[image_id,0]}}
        previous = [guide_id,0]
    for node, key in consumers: node['inputs'][key] = previous
    return result


class GuidedTemplate:
    def __init__(self, template, client, job):
        self.template, self.client, self.job = template, client, job
        self.source_sha256 = template.source_sha256

    def __getattr__(self, name):
        return getattr(self.template, name)

    def resolve(self, request, **kwargs):
        from PIL import Image
        from sprite_h3.backends.comfy_workflow import json_sha256
        resolved = self.template.resolve(request, **kwargs)
        rows = json.loads((self.job/'spec.json').read_text())['guides']
        if not 1 <= len(rows) <= 8: raise ValueError('Require 1-8 guides')
        folder = self.job/'guides'; folder.mkdir(exist_ok=True)
        guides = []
        for i, row in enumerate(rows):
            raw = base64.b64decode(row['png'], validate=True)
            if len(raw)>6*1024*1024: raise ValueError('Guide exceeds 6 MiB')
            with Image.open(io.BytesIO(raw)) as image:
                if image.format != 'PNG' or image.mode != 'RGB' or image.size != (request.width,request.height):
                    raise ValueError('Guide must be an opaque RGB PNG matching the full video canvas')
                image.verify()
            path = folder/f'{i:02d}.png'; path.write_bytes(raw)
            uploaded = self.client.upload_image(path)
            guides.append({'frame':row['frame'],'uploaded':uploaded.node_name,'sha256':hashlib.sha256(raw).hexdigest(),'file':path.name})
        graph = add_guides(resolved.graph, guides)
        (folder/'manifest.json').write_text(json.dumps(guides,indent=2)+'\n')
        # The upstream backend archives this exact graph before submitting it.
        return replace(resolved,graph=graph,resolved_sha256=json_sha256(graph))


def install(job):
    from sprite_h3.backends.comfy import ComfyBackend
    original_init = ComfyBackend.__init__
    def initialize(self, *args, **kwargs):
        original_init(self,*args,**kwargs)
        self.template = GuidedTemplate(self.template,self.client,Path(job))
    ComfyBackend.__init__ = initialize
