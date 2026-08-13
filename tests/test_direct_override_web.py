from http.cookiejar import CookieJar
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import build_opener, HTTPCookieProcessor, Request

from ads_autopilot.owner_override import OwnerOverrideStore
from ads_autopilot.override_web_server import build_server
from ads_autopilot.paths import RuntimePaths
from ads_autopilot.security import hash_password
from ads_autopilot.sealing import bootstrap_key, Sealer

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "correct horse battery staple"


def setup_owner(tmp_path: Path):
    owner_home = tmp_path / "owner"; paths = RuntimePaths.resolve(ROOT, owner_home); paths.ensure_directories(); bootstrap_key(paths.signing_key)
    store = OwnerOverrideStore(paths.owner_db, Sealer.from_path(paths.signing_key).key); policy = json.loads((ROOT / "config/autonomy-policy.json").read_text()); operator = json.loads((ROOT / "config/operator.example.json").read_text()); store.bootstrap(policy, operator, hash_password(PASSWORD)); store.update_operator({"advertiser_account_id": "A1", "profile_ids": ["P1"]}); return paths


def call(opener, url, method="GET", body=None, csrf=None):
    headers = {}; data = None
    if body is not None: data = json.dumps(body).encode(); headers["Content-Type"] = "application/json"
    if csrf: headers["X-CSRF-Token"] = csrf
    response = opener.open(Request(url, data=data, headers=headers, method=method), timeout=5); ctype = response.headers.get("Content-Type", ""); raw = response.read(); return json.loads(raw) if "application/json" in ctype else raw.decode()


def test_owner_web_arms_and_clears_direct_override_with_csrf(tmp_path: Path):
    paths = setup_owner(tmp_path); server = build_server(ROOT, paths.owner_home, host="127.0.0.1", port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start(); base = f"http://127.0.0.1:{server.server_port}"; opener = build_opener(HTTPCookieProcessor(CookieJar()))
    try:
        login = call(opener, base + "/api/login", "POST", {"password": PASSWORD}); csrf = login["csrf"]
        assert "Owner Direct Override" in call(opener, base + "/"); assert "OWNER DIRECT" in call(opener, base + "/static/direct-override.js")
        try: call(opener, base + "/api/direct-override/arm", "POST", {"duration": "30m"})
        except HTTPError as exc: assert exc.code == 403
        else: raise AssertionError("direct override activation must require CSRF")
        armed = call(opener, base + "/api/direct-override/arm", "POST", {"duration": "30m"}, csrf); assert armed["direct_override"]["armed"]; assert armed["direct_override"]["duration"] == "30m"
        state = call(opener, base + "/api/direct-override"); assert state["armed"] and state["return_mode"] == "observe"
        cleared = call(opener, base + "/api/direct-override/clear", "POST", {}, csrf); assert not cleared["direct_override"]["armed"]; assert cleared["mode"] == "observe"
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=2)
