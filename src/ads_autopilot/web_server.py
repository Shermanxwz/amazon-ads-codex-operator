from __future__ import annotations
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import ipaddress,json,mimetypes,os
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs,urlparse
from .owner_store import OwnerStore
from .paths import RuntimePaths
from .security import LoginRateLimiter,SessionStore,constant_token_match,hash_password,verify_password
from .sealing import Sealer
from .state import Store
MAX_BODY=1024*1024; STATIC_NAMES={'index.html','app.js','style.css'}
@dataclass
class WebApp:
    paths:RuntimePaths; owner:OwnerStore; runtime:Store; sessions:SessionStore; login_limiter:LoginRateLimiter; global_limiter:LoginRateLimiter; public_origin:str; session_ttl:int
def build_app(project_root:str|Path,owner_home:str|Path|None=None)->WebApp:
    paths=RuntimePaths.resolve(project_root,owner_home); paths.ensure_directories(); sealer=Sealer.from_path(paths.signing_key); owner=OwnerStore(paths.owner_db,sealer.key); runtime=Store(os.environ.get('ADS_STATE_DB',paths.runtime_db))
    return WebApp(paths,owner,runtime,SessionStore(int(os.environ.get('ADS_WEB_SESSION_TTL','43200')),8),LoginRateLimiter(),LoginRateLimiter(50,300,900),os.environ.get('ADS_WEB_PUBLIC_ORIGIN','').rstrip('/'),int(os.environ.get('ADS_WEB_SESSION_TTL','43200')))
class Handler(BaseHTTPRequestHandler):
    server_version='CodexAdsOwnerControl/0.3'; app:WebApp
    def log_message(self,fmt:str,*args:Any)->None:return
    def _security_headers(self)->None:
        for k,v in [('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Referrer-Policy','no-referrer'),('Permissions-Policy','camera=(), microphone=(), geolocation=(), payment=(), usb=()'),('Cross-Origin-Opener-Policy','same-origin'),('Cross-Origin-Resource-Policy','same-origin'),('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")]:self.send_header(k,v)
    def _respond(self,status:int,data:Any,headers:dict[str,str]|None=None)->None:
        body=json.dumps(data,ensure_ascii=False,separators=(',',':'),default=str).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self._security_headers()
        for k,v in (headers or {}).items():self.send_header(k,v)
        self.end_headers(); self.wfile.write(body)
    def _static(self,filename:str)->None:
        safe=filename.strip('/') or 'index.html'
        if safe not in STATIC_NAMES or '..' in safe:self._respond(404,{'error':'not_found'});return
        try:body=resources.files('ads_autopilot.static').joinpath(safe).read_bytes()
        except FileNotFoundError:self._respond(404,{'error':'not_found'});return
        content_type=mimetypes.guess_type(safe)[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type=='application/javascript':content_type+='; charset=utf-8'
        self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Content-Length',str(len(body)));self._security_headers();self.end_headers();self.wfile.write(body)
    def _body(self)->dict[str,Any]:
        if self.headers.get('Transfer-Encoding'):raise ValueError('transfer encoding is not supported')
        try:length=int(self.headers.get('Content-Length',''))
        except Exception as exc:raise ValueError('invalid Content-Length') from exc
        if length<=0 or length>MAX_BODY:raise ValueError('invalid body size')
        raw=self.rfile.read(length)
        if len(raw)!=length:raise ValueError('request body was truncated')
        try:value=json.loads(raw)
        except Exception as exc:raise ValueError('invalid JSON') from exc
        if not isinstance(value,dict):raise ValueError('JSON body must be an object')
        return value
    def _cookie_sid(self)->str|None:
        item=SimpleCookie(self.headers.get('Cookie','')).get('codex_ads_owner_session');return item.value if item else None
    def _session(self):return self.app.sessions.validate(self._cookie_sid())
    def _require_browser(self,mutate:bool=False)->bool:
        session=self._session()
        if not session:self._respond(401,{'error':'authentication_required'});return False
        if mutate:
            if self.app.public_origin and self.headers.get('Origin','').rstrip('/')!=self.app.public_origin:self._respond(403,{'error':'origin_mismatch'});return False
            if not constant_token_match(self.headers.get('X-CSRF-Token'),session.csrf):self._respond(403,{'error':'csrf_failed'});return False
        return True
    def _login_key(self)->str:
        peer=str(self.client_address[0] or '').strip()
        if peer in {'127.0.0.1','::1'}:
            forwarded=str(self.headers.get('X-Forwarded-For') or '').split(',',1)[0].strip()
            if forwarded:
                try:peer=ipaddress.ip_address(forwarded).compressed
                except ValueError:pass
        try:peer=ipaddress.ip_address(peer).compressed
        except ValueError:peer='unknown'
        return f'ip:{peer}'
    @staticmethod
    def _limit(query:dict[str,list[str]],default:int,maximum:int=1000)->int:
        try:return max(1,min(maximum,int(query.get('limit',[default])[0])))
        except Exception:return default
    def do_GET(self)->None:
        parsed=urlparse(self.path);path,query=parsed.path,parse_qs(parsed.query)
        try:
            if path=='/health/live':self._respond(200,{'ok':True});return
            if path=='/health/ready':
                audit=self.app.owner.verify_audit_chain();runtime=self.app.runtime.integrity_check();status=200 if audit.get('ok') and runtime.get('ok') else 503;self._respond(status,{'ok':status==200,'owner_audit':audit,'runtime_db':runtime});return
            if path=='/api/session':
                session=self._session();self._respond(200,{'authenticated':bool(session),'csrf':session.csrf if session else None});return
            if path=='/':self._static('index.html');return
            if path.startswith('/static/'):self._static(path.removeprefix('/static/'));return
            if not self._require_browser():return
            if path=='/api/dashboard':self._respond(200,self._dashboard())
            elif path=='/api/owner':self._respond(200,self.app.owner.snapshot())
            elif path=='/api/cycles':self._respond(200,{'cycles':self.app.runtime.list_cycles(self._limit(query,50))})
            elif path=='/api/actions':self._respond(200,{'actions':self.app.runtime.list_actions(self._limit(query,200,2000))})
            elif path=='/api/events':self._respond(200,{'events':self.app.runtime.list_events(self._limit(query,200,2000))})
            elif path=='/api/audit':self._respond(200,{'integrity':self.app.owner.verify_audit_chain(),'events':self.app.owner.audit(self._limit(query,200,2000))})
            elif path=='/api/revisions':
                kind=query.get('kind',['policy'])[0];self._respond(200,{'kind':kind,'revisions':self.app.owner.revisions(kind,self._limit(query,50,500))})
            else:self._respond(404,{'error':'not_found'})
        except (ValueError,KeyError) as exc:self._respond(400,{'error':str(exc)})
        except Exception as exc:
            try:self.app.runtime.event('error','web.get_error',None,{'path':path,'error':str(exc)})
            finally:self._respond(500,{'error':'internal_error'})
    def do_POST(self)->None:
        path=urlparse(self.path).path
        try:data=self._body()
        except ValueError as exc:self._respond(400,{'error':str(exc)});return
        try:
            if path=='/api/login':self._login(data);return
            if path=='/api/logout':
                if self._require_browser(mutate=True):self.app.sessions.revoke(self._cookie_sid());self._respond(200,{'ok':True},{'Set-Cookie':'codex_ads_owner_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
                return
            if not self._require_browser(mutate=True):return
            if path=='/api/emergency-stop':self._respond(200,self.app.owner.emergency_stop())
            elif path=='/api/emergency-clear':self._respond(200,self.app.owner.clear_emergency_stop())
            elif path=='/api/revisions/restore':self._respond(200,self.app.owner.restore_revision(str(data.get('kind') or ''),int(data.get('revision') or 0)))
            elif path=='/api/password':
                if not verify_password(str(data.get('current_password') or ''),self.app.owner.get_password_hash()):self._respond(403,{'error':'current_password_invalid'});return
                self.app.owner.update_password_hash(hash_password(str(data.get('new_password') or '')));self.app.sessions.revoke(self._cookie_sid());self._respond(200,{'ok':True,'reauthenticate':True},{'Set-Cookie':'codex_ads_owner_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            else:self._respond(404,{'error':'not_found'})
        except (ValueError,KeyError) as exc:self._respond(400,{'error':str(exc)})
        except Exception as exc:self.app.runtime.event('error','web.post_error',None,{'path':path,'error':str(exc)});self._respond(500,{'error':'internal_error'})
    def do_PUT(self)->None:
        path=urlparse(self.path).path
        try:data=self._body()
        except ValueError as exc:self._respond(400,{'error':str(exc)});return
        if not self._require_browser(mutate=True):return
        try:
            if path=='/api/mode':self._respond(200,self.app.owner.set_mode(str(data.get('mode') or '')))
            elif path=='/api/policy':
                patch=data.get('patch')
                if not isinstance(patch,dict) or not patch:raise ValueError('patch must be a non-empty object')
                self._respond(200,self.app.owner.update_policy(patch))
            elif path=='/api/operator':
                patch=data.get('patch')
                if not isinstance(patch,dict) or not patch:raise ValueError('patch must be a non-empty object')
                self._respond(200,self.app.owner.update_operator(patch))
            else:self._respond(404,{'error':'not_found'})
        except (ValueError,KeyError) as exc:self._respond(400,{'error':str(exc)})
        except Exception as exc:self.app.runtime.event('error','web.put_error',None,{'path':path,'error':str(exc)});self._respond(500,{'error':'internal_error'})
    def _login(self,data:dict[str,Any])->None:
        key=self._login_key();allowed_local,retry_local=self.app.login_limiter.allowed(key);allowed_global,retry_global=self.app.global_limiter.allowed('dashboard-global')
        if not allowed_local or not allowed_global:
            retry=max(retry_local,retry_global,1);self._respond(429,{'error':'login_rate_limited','retry_after':retry},{'Retry-After':str(retry)});return
        if not verify_password(str(data.get('password') or ''),self.app.owner.get_password_hash()):
            local_ok,local_retry=self.app.login_limiter.failure(key);global_ok,global_retry=self.app.global_limiter.failure('dashboard-global');retry=max(local_retry,global_retry);status=401 if local_ok and global_ok else 429;headers={'Retry-After':str(max(retry,1))} if status==429 else None;self._respond(status,{'error':'invalid_credentials' if status==401 else 'login_rate_limited','retry_after':retry},headers);return
        self.app.login_limiter.success(key);sid,csrf=self.app.sessions.create();secure='; Secure' if self.app.public_origin.startswith('https://') else '';cookie=f'codex_ads_owner_session={sid}; HttpOnly; SameSite=Strict{secure}; Path=/; Max-Age={self.app.session_ttl}';self._respond(200,{'ok':True,'csrf':csrf},{'Set-Cookie':cookie})
    def _dashboard(self)->dict[str,Any]:
        return {'owner':self.app.owner.snapshot(),'runtime':self.app.runtime.dashboard(),'owner_audit':self.app.owner.verify_audit_chain(),'paths':{'owner_home':str(self.app.paths.owner_home),'project_root':str(self.app.paths.project_root)}}
def build_server(project_root:str|Path,owner_home:str|Path|None=None,host:str|None=None,port:int|None=None)->ThreadingHTTPServer:
    app=build_app(project_root,owner_home);host=host or os.environ.get('ADS_WEB_HOST','127.0.0.1');port=int(os.environ.get('ADS_WEB_PORT','8765') if port is None else port);handler=type('ConfiguredOwnerHandler',(Handler,),{'app':app});return ThreadingHTTPServer((host,port),handler)
