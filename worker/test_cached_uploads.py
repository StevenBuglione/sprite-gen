"""Exercise the actual upstream multipart/upload boundary without a GPU."""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from cached_sprite_h3 import upload_image


class CachedUploads(unittest.TestCase):
    def test_relocated_identical_png_reuses_name_but_changed_pixels_do_not(self):
        from sprite_h3.backends.comfy_client import ComfyClient
        requests=[]
        def send(method,url,**kwargs):
            self.assertEqual((method,url),('POST','/upload/image'))
            body=kwargs['body'];requests.append(body)
            name=re.search(rb'filename="([^"]+)"',body).group(1).decode()
            self.assertRegex(name,r'^sprite-h3-sha256-[a-f0-9]{64}\.png$')
            self.assertIn(b'name="overwrite"\r\n\r\ntrue',body)
            return {'name':name,'subfolder':'sprite_h3','type':'input'}
        with tempfile.TemporaryDirectory() as temp:
            first=Path(temp)/'one.png';other=Path(temp)/'relocated.png'
            first.write_bytes(b'PNG original content');other.write_bytes(first.read_bytes())
            client=ComfyClient()
            with patch.object(client,'_request_json',side_effect=send):
                a=upload_image(client,first);b=upload_image(client,other)
                self.assertEqual(a.node_name,b.node_name)
                other.write_bytes(b'PNG changed content')
                c=upload_image(client,other)
                self.assertNotEqual(a.node_name,c.node_name)
        self.assertEqual(len(requests),3)


if __name__=='__main__':unittest.main()
