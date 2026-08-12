#!/usr/bin/env python3
from pathlib import Path
import argparse,contextlib,json,sys
try: import fcntl
except ImportError: fcntl=None
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from ads_autopilot.controller import Controller

@contextlib.contextmanager
def single_instance():
    lock_path=ROOT/'state/operator.lock'; lock_path.parent.mkdir(parents=True,exist_ok=True)
    handle=lock_path.open('a+')
    if fcntl is None: raise RuntimeError('Linux fcntl is required for the production single-instance lock')
    try:
        try: fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('another Amazon Ads Codex cycle is already running')
        yield
    finally:
        try: fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
        finally: handle.close()

p=argparse.ArgumentParser(); p.add_argument('kind',choices=['hourly','daily','weekly']); p.add_argument('--dry-run',action='store_true'); a=p.parse_args()
try:
    with single_instance(): result=Controller(ROOT).run(a.kind,a.dry_run)
except Exception as exc:
    result={'status':'exception','error_type':type(exc).__name__,'error':str(exc)}
print(json.dumps(result,indent=2)); raise SystemExit(0 if result['status'] in {'completed','dry_run'} else 3)
