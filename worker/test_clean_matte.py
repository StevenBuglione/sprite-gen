import unittest
import numpy as np
from PIL import Image
import clean_matte

class MatteTests(unittest.TestCase):
    def setUp(self):clean_matte.PROFILE='neutral-warm'

    def test_opaque_approved_palette_survives_and_key_is_transparent(self):
        pixels=np.full((64,64,3),(255,0,255),dtype=np.uint8)
        colors=[(35,35,35),(226,217,194),(133,51,37)]
        for i,color in enumerate(colors):pixels[12:52,10+i*16:22+i*16]=color
        result=np.asarray(clean_matte.recover_edges(Image.fromarray(pixels),'#FF00FF').image)
        for i,color in enumerate(colors):
            self.assertTrue(np.all(result[20:44,12+i*16:20+i*16,:3]==color))
            self.assertTrue(np.all(result[20:44,12+i*16:20+i*16,3]==255))
        self.assertTrue(np.all(result[:8,:,3]==0))

    def test_partial_key_mix_does_not_leave_magenta_or_blue(self):
        pixels=np.full((32,32,3),(255,0,255),dtype=np.uint8)
        pixels[8:24,8:24]=(40,40,40)
        pixels[8:24,7]=(147,20,155)
        result=np.asarray(clean_matte.recover_edges(Image.fromarray(pixels),'#FF00FF').image).astype(int)
        edge=result[10:22,7]
        self.assertTrue(np.all(edge[:,3]>0))
        self.assertTrue(np.all(np.minimum(edge[:,0],edge[:,2])-edge[:,1]<=8))
        self.assertTrue(np.all(edge[:,2]-np.maximum(edge[:,0],edge[:,1])<=7))

    def test_patterned_background_rejected(self):
        image=Image.new('RGB',(32,32),'ivory')
        self.assertFalse(clean_matte.inspect_raw(image)['flat_background'])
        self.assertTrue(clean_matte.inspect_raw(Image.new('RGB',(32,32),'magenta'))['flat_background'])

    def test_general_profile_preserves_blue_artwork(self):
        clean_matte.PROFILE='chroma'
        pixels=np.full((32,32,3),(255,0,255),dtype=np.uint8)
        pixels[8:24,8:24]=(15,50,180)
        result=np.asarray(clean_matte.recover_edges(Image.fromarray(pixels),'#FF00FF').image)
        self.assertTrue(np.all(result[10:22,10:22,:3]==(15,50,180)))

if __name__=='__main__':unittest.main()
