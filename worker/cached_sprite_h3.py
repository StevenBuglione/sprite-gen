"""Run sprite-h3 with content-addressed Comfy input names, scoped to this process.

Identical staged PNGs should reuse image/VAE/text-conditioning caches when only
the noise seed changes. Upstream's random upload names invalidate those caches.
No global Comfy setting or upstream installation is changed. Different bytes
always receive a different SHA256 name; normal prompt/shape cache invalidation
remains ComfyUI's responsibility.
"""
import hashlib
import mimetypes
from pathlib import Path
import uuid


def upload_image(self, image_path: Path, *, subfolder='sprite_h3', overwrite=False):
    from sprite_h3.backends import comfy_client as upstream
    upstream._validate_subfolder(subfolder)
    if not image_path.is_file():
        raise upstream.BackendExecutionError(f'Staged input does not exist: {image_path}')
    image_bytes=image_path.read_bytes()
    suffix=image_path.suffix.lower()
    if not suffix or len(suffix)>12 or not suffix[1:].isalnum():suffix='.png'
    name=f'sprite-h3-sha256-{hashlib.sha256(image_bytes).hexdigest()}{suffix}'
    boundary=f'----sprite-h3-{uuid.uuid4().hex}'
    body=upstream._encode_multipart(boundary,
        fields={'type':'input','subfolder':subfolder,'overwrite':'true'},
        file_field='image',filename=name,
        content_type=mimetypes.guess_type(name)[0] or 'application/octet-stream',
        content=image_bytes)
    payload=self._request_json('POST','/upload/image',body=body,
        headers={'Content-Type':f'multipart/form-data; boundary={boundary}'})
    return upstream._uploaded_image_from_payload(payload)


def main():
    from sprite_h3.backends.comfy_client import ComfyClient
    from sprite_h3.cli import main as upstream_main
    ComfyClient.upload_image=upload_image
    return upstream_main()


if __name__=='__main__':raise SystemExit(main())
