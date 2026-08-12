#!/usr/bin/env python3
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]
base=ROOT/'vendor/amazon-postman/postman/repo/postman'; out=ROOT/'vendor/amazon-postman/index'; out.mkdir(parents=True,exist_ok=True)
rows=[]
def walk(items,prefix=[]):
    for item in items:
        path=prefix+[item.get('name','')]
        if isinstance(item.get('item'),list): walk(item['item'],path)
        elif isinstance(item.get('request'),dict):
            req=item['request']; url=req.get('url',{}); raw=url.get('raw') if isinstance(url,dict) else str(url)
            rows.append({'name':' / '.join(path),'method':req.get('method'),'url':raw})
for p in base.glob('*.postman_collection.json'):
    try: walk(json.loads(p.read_text()).get('item',[]),[p.name])
    except Exception: pass
(out/'endpoints.json').write_text(json.dumps(rows,indent=2))
print(f'indexed {len(rows)} endpoints')
