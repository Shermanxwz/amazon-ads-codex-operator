#!/usr/bin/env python3
from __future__ import annotations
import compileall, hashlib, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks=[]
def add(ok,msg): checks.append((bool(ok),msg)); print(('[OK]   ' if ok else '[FAIL] ')+msg)

def source_files():
    allowed={'.py','.md','.json','.toml','.sh','.html','.js','.css','.txt'}
    skip={'.git','.pytest_cache','__pycache__','.venv','vendor'}
    for p in ROOT.rglob('*'):
        if not p.is_file() or any(x in p.parts for x in skip) or p.suffix not in allowed: continue
        yield p

def main():
    add(compileall.compile_dir(ROOT/'src',quiet=1) and compileall.compile_dir(ROOT/'scripts',quiet=1), 'Python source compiles')
    cp=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    print(cp.stdout.rstrip()); add(cp.returncode==0,'Test suite passes')
    for p in [ROOT/'config/autonomy-policy.json',ROOT/'config/operator.example.json',*sorted((ROOT/'schemas').glob('*.json'))]:
        try: json.loads(p.read_text()); ok=True
        except Exception: ok=False
        add(ok,f'JSON parses: {p.relative_to(ROOT)}')
    for name in ('index.html','app.js','style.css'):
        add((ROOT/'src/ads_autopilot/static'/name).exists(),f'Owner Web asset present: {name}')
    add('version = "0.3.0"' in (ROOT/'pyproject.toml').read_text(),'Package version is v0.3.0')
    add('__version__ = "0.3.0"' in (ROOT/'src/ads_autopilot/__init__.py').read_text(),'Runtime package version is v0.3.0')
    cfg=(ROOT/'.codex/config.toml').read_text()
    add('default_tools_approval_mode = "writes"' in cfg,'Project MCP config is write-gated by default')
    runner=(ROOT/'src/ads_autopilot/codex_runner.py').read_text(); controller=(ROOT/'src/ads_autopilot/controller.py').read_text()
    add('--sandbox' in runner and '"read-only"' in runner,'Codex shell sandbox is read-only')
    add('"--json"' in runner,'Codex JSONL event-stream forensic logging enabled')
    add('enabled_tools' in runner and 'allowed_mcp_tools' in runner,'Atomic Executor constrains MCP enabled_tools')
    add('grant_path=grant_path' in controller and '_write_executor_grant' in controller,'Controller mints per-action signed grants')
    add((ROOT/'scripts/codex_pretool_hook.py').exists(),'Self-contained frozen hook source exists')
    hook=(ROOT/'scripts/codex_pretool_hook.py').read_text()
    add('tool in {"Bash","apply_patch","Edit","Write"}' in hook,'Frozen hook blocks local shell/file mutation tools in read-only roles')
    add('executor may only call amazon_ads MCP' in hook and 'MCP arguments differ from sealed grant' in hook,'Frozen hook fails closed to exact Executor MCP tool + arguments')
    web=(ROOT/'src/ads_autopilot/web_server.py').read_text()
    add('ADS_WEB_HOST' in web and '127.0.0.1' in web,'Owner Web binds loopback by default')
    add('X-CSRF-Token' in web and 'csrf_failed' in web,'Owner Web mutations require CSRF token')
    add('/api/emergency-stop' in web and '/api/revisions/restore' in web,'Owner Web exposes emergency stop and revision rollback')

    sh_files=sorted((ROOT/'scripts').glob('*.sh'))
    for sh in sh_files:
        cp_sh=subprocess.run(['bash','-n',str(sh)],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        add(cp_sh.returncode==0,f'Shell syntax valid: {sh.name}')

    with tempfile.TemporaryDirectory() as wheel_dir:
        cp_wheel=subprocess.run([sys.executable,'-m','pip','wheel','.', '--no-deps','--no-build-isolation','-w',wheel_dir],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        wheels=list(Path(wheel_dir).glob('*.whl'))
        wheel_ok=cp_wheel.returncode==0 and len(wheels)==1
        add(wheel_ok,'Offline wheel build succeeds with installed build toolchain')
        if wheel_ok:
            with zipfile.ZipFile(wheels[0]) as zf:
                names=set(zf.namelist())
            required={'ads_autopilot/static/index.html','ads_autopilot/static/app.js','ads_autopilot/static/style.css'}
            add(required.issubset(names),'Wheel contains Owner Web static assets')

    forbidden_names={'owner.db','runtime.db','operator_signing_key','auth.json'}
    leaked=[str(p.relative_to(ROOT)) for p in ROOT.rglob('*') if p.is_file() and p.name in forbidden_names and '.git' not in p.parts]
    add(not leaked,'No runtime Owner/auth files in repository tree'+(f': {leaked}' if leaked else ''))
    patterns=[
      ('Amazon OAuth client id',re.compile(r'amzn1\.application-oa2-client\.[A-Za-z0-9._-]{12,}')),
      ('Bearer token',re.compile(r'Bearer\s+[A-Za-z0-9._~+/=-]{24,}')),
      ('PEM private key',re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
      ('AWS access key',re.compile(r'\bAKIA[0-9A-Z]{16}\b')),
    ]
    text='\n'.join(p.read_text(errors='ignore') for p in source_files())
    for label,pat in patterns: add(not pat.search(text),f'No {label} pattern in source')

    if shutil.which('systemd-analyze'):
        with tempfile.TemporaryDirectory() as td:
            td_path=Path(td); rendered_units=[]
            for src in sorted((ROOT/'systemd').glob('*')):
                if not src.is_file(): continue
                rendered=(src.read_text().replace('@ROOT@','/opt/amazon-ads-codex-operator')
                          .replace('@OWNER_HOME@','/var/lib/amazon-ads-codex-owner')
                          .replace('@DAILY_HOUR@','04').replace('@WEEKLY_DAY@','Sun')
                          .replace('@WEEKLY_HOUR@','05').replace('@TIMEZONE@','UTC'))
                dest=td_path/src.name; dest.write_text(rendered); rendered_units.append(str(dest))
                if src.suffix=='.timer':
                    cal=next((line.split('=',1)[1].strip() for line in rendered.splitlines() if line.startswith('OnCalendar=')),None)
                    cp2=subprocess.run(['systemd-analyze','calendar',cal],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT) if cal else None
                    add(bool(cp2 and cp2.returncode==0),f'Valid systemd calendar: {src.name}')
            verify=subprocess.run(['systemd-analyze','verify',*rendered_units],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            add(verify.returncode==0,'Rendered systemd service/timer units verify cleanly')
    else: print('[WARN] systemd-analyze unavailable; systemd validation skipped')
    print(f'\n{sum(ok for ok,_ in checks)}/{len(checks)} checks passed')
    return 0 if all(ok for ok,_ in checks) else 2
if __name__=='__main__': raise SystemExit(main())
