from http.cookiejar import CookieJar
import json
from pathlib import Path
import threading
from urllib.request import build_opener, HTTPCookieProcessor, Request
from urllib.error import HTTPError
from ads_autopilot.owner_store import OwnerStore
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.security import hash_password
from ads_autopilot.sealing import bootstrap_key,Sealer
from ads_autopilot.web_server import build_server
ROOT=Path(__file__).resolve().parents[1]; PASSWORD='correct horse battery staple'
def setup_owner(tmp_path:Path):
    owner_home=tmp_path/'owner'; paths=RuntimePaths.resolve(ROOT,owner_home); paths.ensure_directories(); bootstrap_key(paths.signing_key); store=OwnerStore(paths.owner_db,Sealer.from_path(paths.signing_key).key); p=json.loads((ROOT/'config/autonomy-policy.json').read_text()); o=json.loads((ROOT/'config/operator.example.json').read_text()); store.bootstrap(p,o,hash_password(PASSWORD)); return paths
def call(opener,url,method='GET',body=None,csrf=None):
    headers={}; data=None
    if body is not None:data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    if csrf:headers['X-CSRF-Token']=csrf
    r=opener.open(Request(url,data=data,headers=headers,method=method),timeout=5); return json.loads(r.read())
def test_web_requires_login_and_csrf_and_updates_owner_policy(tmp_path:Path):
    paths=setup_owner(tmp_path); server=build_server(ROOT,paths.owner_home,host='127.0.0.1',port=0); t=threading.Thread(target=server.serve_forever,daemon=True); t.start(); base=f'http://127.0.0.1:{server.server_port}'; opener=build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        try:call(opener,base+'/api/dashboard')
        except HTTPError as e:assert e.code==401
        else:raise AssertionError('dashboard must require auth')
        login=call(opener,base+'/api/login','POST',{'password':PASSWORD}); csrf=login['csrf']; dash=call(opener,base+'/api/dashboard'); assert dash['owner']['mode']=='observe'
        try:call(opener,base+'/api/policy','PUT',{'patch':{'money.owner_daily_spend_ceiling':250}})
        except HTTPError as e:assert e.code==403
        else:raise AssertionError('mutation must require CSRF')
        changed=call(opener,base+'/api/policy','PUT',{'patch':{'money.owner_daily_spend_ceiling':250}},csrf); assert changed['policy']['money']['owner_daily_spend_ceiling']==250; revs=call(opener,base+'/api/revisions?kind=policy&limit=10')['revisions']; assert len(revs)>=2; restored=call(opener,base+'/api/revisions/restore','POST',{'kind':'policy','revision':revs[-1]['revision']},csrf); assert restored['mode']=='observe'; stop=call(opener,base+'/api/emergency-stop','POST',{},csrf); assert stop['emergency_stop'] and stop['mode']=='paused'; ready=call(opener,base+'/health/ready'); assert ready['ok']
    finally:server.shutdown(); server.server_close(); t.join(timeout=2)
