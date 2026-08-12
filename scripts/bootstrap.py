#!/usr/bin/env python3
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]
import sys; sys.path.insert(0,str(ROOT/'src'))
from ads_autopilot.sealing import bootstrap_key
p=bootstrap_key(ROOT)
for src,dst in [('config/operator.example.json','config/operator.local.json'),('config/autonomy-policy.json','config/autonomy-policy.local.json')]:
    d=ROOT/dst
    if not d.exists(): shutil.copy2(ROOT/src,d)
print(f'Created/verified signing key: {p}')
print('Created local config copies if absent. Edit operator.local.json and set owner_daily_spend_ceiling before live spend increases.')
