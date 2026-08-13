#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ads_autopilot.owner_override import OwnerOverrideStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.sealing import Sealer

def store():
    paths=RuntimePaths.resolve(ROOT)
    return OwnerOverrideStore(paths.owner_db,Sealer.from_path(paths.signing_key).key)

def main():
    ap=argparse.ArgumentParser(description='Local trusted Owner emergency/control CLI')
    sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('status'); m=sub.add_parser('mode'); m.add_argument('value',choices=['autopilot','observe','paused'])
    sub.add_parser('direct-clear'); sub.add_parser('emergency-stop'); sub.add_parser('emergency-clear'); sub.add_parser('verify-audit')
    ns=ap.parse_args(); s=store()
    if ns.cmd=='status': out=s.snapshot()
    elif ns.cmd=='mode': out=s.set_mode(ns.value,actor='ownerctl')
    elif ns.cmd=='direct-clear': out=s.clear_direct_override(actor='ownerctl')
    elif ns.cmd=='emergency-stop': out=s.emergency_stop(actor='ownerctl')
    elif ns.cmd=='emergency-clear': out=s.clear_emergency_stop(actor='ownerctl')
    else: out=s.verify_audit_chain()
    print(json.dumps(out,ensure_ascii=False,indent=2)); return 0 if out.get('ok',True) else 2
if __name__=='__main__': raise SystemExit(main())
