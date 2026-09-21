#!/usr/bin/env python3
"""Key extraction with foreground-color recovery at partially covered edges.

Runs in sprite-h3's Python environment. The chroma profile preserves non-key
colors. The opt-in neutral-warm profile preserves the approved warm/neutral
palette and suppresses cool contamination, including opaque contaminated pixels.
The original lossless video frames and every prior processing revision survive.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from sprite_h3.processing.background import remove_key_background, BackgroundRemovalResult, measure_foreground

PROFILE = "neutral-warm"
_base_remove = remove_key_background

def recover_edges(image: Image.Image, key_color, **kwargs) -> BackgroundRemovalResult:
    kwargs.update(matte="chroma", chroma_tolerance=8, alpha_power=1.5, minimum_alpha=16)
    base = _base_remove(image, key_color, **kwargs)
    if PROFILE == "chroma": return base
    # Explicitly opt-in for artwork whose approved palette contains ivory,
    # charcoal and warm colors, with no intentional blue or purple paint.
    # This preserves native antialiasing; no nearest-color fills or erosion.
    values = np.asarray(base.image,dtype=np.float64)/255
    magenta = np.maximum(0,np.minimum(values[...,0],values[...,2])-values[...,1]-.025)
    values[...,0] = np.maximum(0,values[...,0]-magenta)
    values[...,2] = np.maximum(0,values[...,2]-magenta)
    blue = np.maximum(0,values[...,2]-np.maximum(values[...,0],values[...,1])-.02)
    values[...,2] -= blue
    values[...,3] *= 1-np.clip(magenta*2.2+blue*1.5,0,1)
    # A magenta edge can leave a cyan remainder after asymmetric channel spill.
    green = np.maximum(0,values[...,1]-values[...,0]-.02)
    values[...,1] -= green
    values[...,2] = np.minimum(values[...,2],values[...,1]+.02)
    # Extend genuine opaque colors into the translucent antialias band. Keep
    # coverage unchanged: refitting alpha here would chew up hair and blade tips.
    core = values[...,3]>=.98
    if np.any(core):
        distance,indices=ndimage.distance_transform_edt(~core,return_indices=True)
        neighbors=values[indices[0],indices[1],:3]
        band=(values[...,3]>0)&(values[...,3]<.90)&(distance<=3)
        values[band,:3]=neighbors[band]
    output = np.round(np.clip(values,0,1)*255).astype(np.uint8)
    output[output[...,3]==0] = 0
    result = Image.fromarray(output,"RGBA")
    return BackgroundRemovalResult(result,base.estimated_background,measure_foreground(result),
        int(np.count_nonzero(output[...,3]==0)),int(np.count_nonzero((output[...,3]>0)&(output[...,3]<255))),int(np.count_nonzero((magenta+blue)>0)))

def inspect_raw(image: Image.Image, key=(255,0,255)) -> dict:
    rgb = np.asarray(image.convert("RGB"),dtype=np.float64)
    border = np.concatenate((rgb[0],rgb[-1],rgb[1:-1,0],rgb[1:-1,-1]))
    distances = np.linalg.norm(border-np.asarray(key),axis=1)
    ratio = float(np.mean(distances<60))
    foreground_fraction=float(np.mean(np.linalg.norm(rgb-np.asarray(key),axis=2)>60))
    return {"border_key_fraction":ratio,"non_key_fraction":foreground_fraction,"flat_background":ratio>=.97 and foreground_fraction<=.55}

def main():
    global PROFILE
    p=argparse.ArgumentParser()
    commands=p.add_subparsers(dest="command",required=True)
    one=commands.add_parser("frame")
    one.add_argument("source",type=Path);one.add_argument("out",type=Path)
    one.add_argument("--profile",choices=["chroma","neutral-warm"],default="chroma")
    one.add_argument("--key",default="#FF00FF")
    run=commands.add_parser("reprocess")
    run.add_argument("run",type=Path)
    run.add_argument("--profile",choices=["chroma","neutral-warm"],default="chroma")
    run.add_argument("--key",default="#FF00FF")
    a=p.parse_args()
    PROFILE=a.profile
    key=tuple(int(a.key.lstrip('#')[i:i+2],16) for i in (0,2,4))
    if a.command=="frame":
        im=Image.open(a.source)
        result=recover_edges(im,a.key,hard_threshold=48,soft_threshold=80)
        result.image.save(a.out)
        print(json.dumps(inspect_raw(im,key)))
        return
    from sprite_h3.config import load_config
    from sprite_h3.services.reprocess import process_existing_run
    import sprite_h3.services.process as processing
    processing.remove_key_background=recover_edges
    config=load_config('/home/olfa/ai/sprite_h3/config.local.toml')
    overrides={"processing":{"background_matte":"chroma","background_chroma_tolerance":8,"background_alpha_power":1.5,"background_minimum_alpha":16}}
    outcome=process_existing_run(a.run,config,overrides=overrides)
    report={"profile":PROFILE,"script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"key_color":a.key,"cells":[],"usable":True}
    for cell in sorted((a.run/'actions').glob('*/*')):
        raw=sorted((cell/'raw/frames').glob('*.png'))
        if not raw: continue
        bad=[]
        for i,path in enumerate(raw):
            with Image.open(path) as image:
                result=inspect_raw(image,key)
            if not result['flat_background']:bad.append({"frame":i,**result})
        revisions=sorted((cell/'processing').glob('*/revision.json'))
        latest=json.loads(revisions[-1].read_text())
        usable=not bad and latest.get('status')=='completed'
        residue=0
        for png in sorted((revisions[-1].parent/'frames/rgba').glob('*.png')):
            with Image.open(png) as image: pixels=np.asarray(image,dtype=np.int16)
            if PROFILE=='neutral-warm':
                cool=(np.minimum(pixels[...,0],pixels[...,2])-pixels[...,1]>10)|(pixels[...,2]-np.maximum(pixels[...,0],pixels[...,1])>10)|(pixels[...,1]-pixels[...,0]>10)
                residue+=int(np.count_nonzero(cool&(pixels[...,3]>=16)))
        usable=usable and residue==0
        report['cells'].append({"cell":str(cell.relative_to(a.run)),"revision":str(revisions[-1].relative_to(a.run)),"frame_count":len(raw),"background_failures":bad,"residual_key_color_pixels":residue,"usable":usable})
        report['usable'] &= usable
    (a.run/'matte-quality.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()

