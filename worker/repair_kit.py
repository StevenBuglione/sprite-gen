#!/usr/bin/env python3
"""Re-extract and repack a returned kit without another video generation."""
import argparse
import json
import subprocess
from pathlib import Path
from run_job import collect_artifacts, CLI, PY

p=argparse.ArgumentParser()
p.add_argument('manifest',type=Path)
p.add_argument('out',type=Path)
p.add_argument('--profile',choices=['chroma','neutral-warm'],default='chroma')
a=p.parse_args()
if a.out.exists(): raise SystemExit('Refusing to replace an existing repaired kit')
manifest=json.loads(a.manifest.read_text())
run=Path(manifest['run'])
spec=manifest['spec']
spec['matte_profile']=a.profile
subprocess.run([str(PY),str(Path(__file__).with_name('clean_matte.py')),'reprocess',str(run),'--profile',a.profile,'--key',spec.get('chroma','#FF00FF')],check=True)
for command in ['review','curate','pack']:
    args=[str(CLI),command,str(run),'--action',spec['action'],'--facing',spec['facing']]
    if command=='curate':args.append('--accept-suggestions')
    subprocess.run(args,check=True)
collect_artifacts(a.out,spec,run,run/'actions'/spec['action']/spec['facing'])
print(json.dumps({'out':str(a.out),'run':str(run)}))
