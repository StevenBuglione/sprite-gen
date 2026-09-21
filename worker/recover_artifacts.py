"""Recover an existing video + full frames without submitting another GPU job."""
import argparse
from pathlib import Path
from run_job import collect_artifacts, load_spec

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job',type=Path)
    parser.add_argument('run',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--matte-profile',choices=['chroma','neutral-warm','deferred'])
    args=parser.parse_args()
    if args.out.exists():parser.error('Recovery output must be a new directory')
    spec=load_spec(args.job)
    if args.matte_profile:spec['matte_profile']=args.matte_profile
    cell=args.run/'actions'/spec['action']/spec['facing']
    collect_artifacts(args.out,spec,args.run,cell,pack_warning='Recovered existing generation; preview atlas may be unavailable.')
    print(args.out)

if __name__=='__main__':main()
