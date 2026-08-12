from __future__ import annotations
import hmac, hashlib, os, secrets
from pathlib import Path
from typing import Any
from .canonical import canonical_json,digest

class Sealer:
    def __init__(self,key:bytes): self.key=key
    @classmethod
    def from_runtime(cls,root:str|Path):
        env=os.environ.get('ADS_OPERATOR_SIGNING_KEY')
        if env: return cls(env.encode())
        p=Path(root)/'.secrets/operator_signing_key'
        if not p.exists(): raise RuntimeError('signing key missing; run scripts/bootstrap.py')
        return cls(p.read_bytes().strip())
    def sign(self,value:Any)->str: return hmac.new(self.key,canonical_json(value).encode(),hashlib.sha256).hexdigest()
    def verify(self,value:Any,signature:str)->bool: return hmac.compare_digest(self.sign(value),signature)
    def seal_action(self,base:dict[str,Any],*,policy_hash:str,plan_hash:str,operator_hash:str)->dict[str,Any]:
        body=dict(base)
        body['policy_hash']=policy_hash; body['plan_hash']=plan_hash; body['operator_hash']=operator_hash
        body['action_hash']=digest(body)
        body['signature']=self.sign(body)
        return body

def bootstrap_key(root:str|Path)->Path:
    p=Path(root)/'.secrets/operator_signing_key'; p.parent.mkdir(parents=True,exist_ok=True)
    if not p.exists():
        p.write_text(secrets.token_urlsafe(48)); os.chmod(p,0o600)
    return p
