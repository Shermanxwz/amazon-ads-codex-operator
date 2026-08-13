#!/usr/bin/env python3
from __future__ import annotations
import compileall, json, re, shutil, subprocess, sys, tempfile, tomllib, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
checks:list[tuple[bool,str]]=[]
def add(ok,msg): checks.append((bool(ok),msg)); print(("[OK]   " if ok else "[FAIL] ")+msg)
def text(p): return (ROOT/p).read_text()
def has(p,*tokens):
    s=text(p); return all(t in s for t in tokens)
def run(*args): return subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)

def source_files():
    allowed={".py",".md",".json",".toml",".sh",".html",".js",".css",".txt",".yml",".yaml"}
    skip={".git",".pytest_cache","__pycache__",".venv",".acceptance-venv","vendor","virtual-dist"}
    return [p for p in ROOT.rglob("*") if p.is_file() and p.suffix in allowed and not any(x in skip for x in p.parts)]

def main():
    add(compileall.compile_dir(ROOT/"src",quiet=1) and compileall.compile_dir(ROOT/"scripts",quiet=1),"Python source compiles")
    tests=run(sys.executable,"-m","pytest","-q"); print(tests.stdout.rstrip()); add(tests.returncode==0,"Test suite passes")
    jsons=["config/autonomy-policy.json","config/operator.example.json","config/codex-compatibility.json","vendor/amazon-postman/CERTIFIED_UPSTREAM.json",".agents/plugins/marketplace.json","plugins/amazon-ads-operator/.codex-plugin/plugin.json"]+[str(p.relative_to(ROOT)) for p in sorted((ROOT/"schemas").glob("*.json"))]
    for rel in jsons:
        try: json.loads(text(rel)); ok=True
        except Exception: ok=False
        add(ok,f"JSON parses: {rel}")

    version=str(tomllib.loads(text("pyproject.toml")).get("project",{}).get("version") or "")
    m=re.search(r'__version__\s*=\s*["\']([^"\']+)',text("src/ads_autopilot/__init__.py")); runtime=m.group(1) if m else ""
    plugin=json.loads(text("plugins/amazon-ads-operator/.codex-plugin/plugin.json"))
    add(bool(re.fullmatch(r"\d+\.\d+\.\d+",version)),f"Package semver valid: {version}")
    add(runtime==version and plugin.get("version")==version,"Package/runtime/plugin versions agree")
    add((ROOT/f"docs/RELEASE_V{version}.md").exists(),f"Release notes exist for v{version}")
    add(plugin.get("skills")=="./skills/" and all((ROOT/f"plugins/amazon-ads-operator/skills/{s}/SKILL.md").exists() for s in ("ads-status","ads-diagnose","ads-acceptance","ads-autonomy")),"Codex plugin/skills complete")
    market=json.loads(text(".agents/plugins/marketplace.json")); add(any(x.get("name")=="amazon-ads-operator" and (x.get("source") or {}).get("path")=="./plugins/amazon-ads-operator" for x in market.get("plugins",[])),"Repo marketplace exposes plugin")
    add(all((ROOT/f"src/ads_autopilot/static/{n}").exists() for n in ("index.html","app.js","style.css")),"Owner Web assets present")

    add('default_tools_approval_mode = "writes"' in text(".codex/config.toml"),"Project MCP config write-gated")
    add(has("src/ads_autopilot/codex_runner.py","--sandbox",'"read-only"','"--json"',"enabled_tools","allowed_mcp_tools","--strict-config","--ephemeral","resolve_active_binary","owner-pinned-active",".runtime.json"),"Runner isolation, exact tools and ACTIVE identity evidence present")
    add(has("src/ads_autopilot/controller.py",'"version": 2',"_write_executor_grant","_recover_incomplete_actions","recovery_uncertain","_check_live_state","stale_prewrite"),"Controller one-use, fresh-state and crash recovery contracts present")

    hook=text("scripts/codex_pretool_hook.py")
    add(all(t in hook for t in ("verify_live_owner_authority","Owner emergency stop is active","O_EXCL","grant already consumed","MCP arguments differ from sealed grant")),"Frozen hook final-boundary/replay/exact-args guards present")
    add(has("src/ads_autopilot/sealing.py","executor_grant_signing_key","_GRANT_KDF_CONTEXT") and "grant_signing_key" in text("src/ads_autopilot/paths.py"),"Executor grant signing is domain-separated")
    add("executor_grant_signing_key" in hook and "operator_signing_key" not in hook and "domain-separated" in text("scripts/preflight.py"),"Frozen hook cannot read Owner master signing key")
    add(not (ROOT/"src/ads_autopilot/hook_policy.py").exists(),"No duplicate hook implementation")

    compat=json.loads(text("config/codex-compatibility.json")); names={str(x.get("name")) for x in compat.get("required_commands",[])}; exec_cfg=next(x for x in compat.get("required_commands",[]) if x.get("name")=="exec"); tokens=set(exec_cfg.get("required_tokens",[]))
    add(compat.get("version")==2 and compat.get("strategy")=="capability-gated-evergreen" and compat.get("production_runtime")=="owner-pinned-active-slot","Codex Evergreen v2 contract enabled")
    add({"exec","mcp","plugin","features","sandbox"}.issubset(names) and {"--strict-config","--output-schema","--json","--sandbox"}.issubset(tokens),"Stable Codex command/flag contract complete")
    add(has("src/ads_autopilot/codex_compat/registry.py","candidates","active","previous","promote_candidate","rollback_runtime","slots_root","file_sha256","os.replace","os.fsync","flock"),"Codex runtime registry is content-addressed, atomic and serialized")
    add(has("scripts/bootstrap.py","if active_identity(paths) is not None","register_candidate","bootstrap_executor_grant_key"),"Bootstrap preserves ACTIVE and initializes grant key")
    add(has("scripts/configure_amazon_mcp.sh","resolve_active_binary",'"$CODEX_BIN" mcp login amazon_ads'),"Amazon MCP setup uses ACTIVE Codex")
    install=text("scripts/install_codex_ubuntu.sh"); add("candidate --binary" in install and not re.search(r"codex_runtime\.py[\"']?\s+promote\b",install),"Codex update registers candidate only")

    add(has("scripts/backup_owner.py",'"version": 2',"snapshot_codex_runtimes","codex_runtime_snapshot","executor_grant_signing_key","active_id","previous_id","binary_sha256"),"Backup v2 preserves signing domains and Codex runtime identities")
    add(has("scripts/restore_owner.py","_restore_codex_runtimes","save_registry","active_identity","_reset_unrestored_surfaces","codex_home","grant_root",'"-wal"'),"Restore verifies/rebinds runtimes and scrubs stale state")
    add((ROOT/"tests/test_backup_restore.py").exists(),"Disaster-recovery tests present")

    virtual=text("scripts/virtual_acceptance.py"); fixture=text("tests/fixtures/virtual_codex.py")
    scenarios=("fresh-bootstrap-preflight","sealed-live-happy-path","ambiguous-after-write-reconciled","consume-before-write-never-replayed","emergency-final-boundary-and-flock")
    add(all(s in virtual for s in scenarios),"Virtual acceptance covers happy, ambiguity, restart, Emergency Stop and flock")
    add("codex_pretool_hook.py" in fixture and "register_candidate" in virtual and "restore_backup" in virtual,"Virtual acceptance crosses frozen hook, Evergreen and disaster recovery")

    amazon=json.loads(text("vendor/amazon-postman/CERTIFIED_UPSTREAM.json")); add(bool(re.fullmatch(r"[0-9a-f]{40}",str(amazon.get("commit") or ""))),"Amazon contract pinned to immutable commit")
    add(has("scripts/sync_amazon_postman.sh","CERTIFIED_UPSTREAM.json",'fetch --depth 1 origin "$PIN"'),"Amazon sync consumes certified pin")
    add(has("src/ads_autopilot/web_server.py","ADS_WEB_HOST","127.0.0.1","X-CSRF-Token","csrf_failed","/api/emergency-stop","/api/revisions/restore"),"Owner Web loopback/CSRF/emergency/rollback guards present")

    workflows={n:ROOT/f".github/workflows/{p}" for n,p in {"archive":"archive.yml","release":"release.yml","evergreen":"codex-evergreen.yml","single-main":"branch-hygiene.yml"}.items()}
    for n,p in workflows.items(): add(p.exists(),f"GitHub workflow present: {n}")
    add(all(t in workflows["release"].read_text() for t in ("workflow_run","archive-gate","RELEASE_SHA","SHA256SUMS")),"Release binds exact green main SHA and checksums")
    add("Delete every non-main branch" in workflows["single-main"].read_text(),"Branch hygiene enforces main-only")
    add(all(t in workflows["evergreen"].read_text() for t in ("chatgpt.com/codex/install.sh","check_codex_runtime.py")),"Daily current-Codex compatibility drift probe present")
    add(all(t in workflows["archive"].read_text() for t in ("virtual-full-stack","virtual_acceptance.py",".acceptance-venv")),"Archive workflow requires isolated virtual full stack")

    for sh in sorted((ROOT/"scripts").glob("*.sh")): add(run("bash","-n",str(sh)).returncode==0,f"Shell syntax valid: {sh.name}")
    with tempfile.TemporaryDirectory() as d:
        wheel=run(sys.executable,"-m","pip","wheel",".","--no-deps","--no-build-isolation","-w",d); files=list(Path(d).glob("*.whl")); ok=wheel.returncode==0 and len(files)==1; add(ok,"Offline wheel build succeeds")
        if ok:
            with zipfile.ZipFile(files[0]) as z: names=set(z.namelist())
            req={"ads_autopilot/static/index.html","ads_autopilot/static/app.js","ads_autopilot/static/style.css","ads_autopilot/codex_compat/registry.py","ads_autopilot/codex_compat/probe.py"}; add(req.issubset(names),"Wheel contains required runtime/Web assets")

    forbidden={"owner.db","runtime.db","operator_signing_key","executor_grant_signing_key","auth.json","registry.json"}
    leaked=[str(p.relative_to(ROOT)) for p in ROOT.rglob("*") if p.is_file() and p.name in forbidden and ".git" not in p.parts]; add(not leaked,"No runtime Owner/auth/key/registry files committed"+(f": {leaked}" if leaked else ""))
    combined="\n".join(p.read_text(errors="ignore") for p in source_files())
    for label,pat in (("Amazon OAuth client id",r"amzn1\.application-oa2-client\.[A-Za-z0-9._-]{12,}"),("Bearer token",r"Bearer\s+[A-Za-z0-9._~+/=-]{24,}"),("PEM private key",r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),("AWS access key",r"\bAKIA[0-9A-Z]{16}\b")):
        add(re.search(pat,combined) is None,f"No {label} pattern in source")

    if shutil.which("systemd-analyze"):
        with tempfile.TemporaryDirectory() as d:
            rendered=[]
            for src in sorted((ROOT/"systemd").glob("*")):
                if not src.is_file(): continue
                s=src.read_text().replace("@ROOT@","/opt/amazon-ads-codex-operator").replace("@OWNER_HOME@","/var/lib/amazon-ads-codex-owner").replace("@DAILY_HOUR@","04").replace("@WEEKLY_DAY@","Sun").replace("@WEEKLY_HOUR@","05").replace("@TIMEZONE@","UTC")
                dst=Path(d)/src.name; dst.write_text(s); rendered.append(str(dst))
                if src.suffix==".timer":
                    cal=next((x.split("=",1)[1].strip() for x in s.splitlines() if x.startswith("OnCalendar=")),None); add(bool(cal and run("systemd-analyze","calendar",cal).returncode==0),f"Valid systemd calendar: {src.name}")
            add(run("systemd-analyze","verify",*rendered).returncode==0,"Rendered systemd units verify")
    else: print("[WARN] systemd-analyze unavailable; systemd validation skipped")

    passed=sum(ok for ok,_ in checks); print(f"\n{passed}/{len(checks)} checks passed"); return 0 if passed==len(checks) else 2
if __name__=="__main__": raise SystemExit(main())
