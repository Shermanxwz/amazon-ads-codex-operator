from __future__ import annotations

from http.server import ThreadingHTTPServer
from importlib import resources
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

from .owner_override import OwnerOverrideStore
from .sealing import Sealer
from .web_server import Handler, WebApp, build_app as build_base_app


class OwnerOverrideHandler(Handler):
    def _static(self, filename: str) -> None:
        safe = filename.strip("/") or "index.html"
        if safe != "direct-override.js":
            return super()._static(filename)
        try:
            body = resources.files("ads_autopilot.static").joinpath(safe).read_bytes()
        except FileNotFoundError:
            self._respond(404, {"error": "not_found"}); return
        content_type = mimetypes.guess_type(safe)[0] or "application/javascript"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self._security_headers(); self.end_headers(); self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/direct-override":
            return super().do_GET()
        if not self._require_browser():
            return
        try:
            self._respond(200, self.app.owner.direct_override_state())
        except (ValueError, KeyError) as exc:
            self._respond(400, {"error": str(exc)})
        except Exception as exc:
            self.app.runtime.event("error", "web.direct_override_get_error", None, {"error": str(exc)}); self._respond(500, {"error": "internal_error"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/direct-override/arm", "/api/direct-override/clear"}:
            return super().do_POST()
        try:
            data = self._body()
        except ValueError as exc:
            self._respond(400, {"error": str(exc)}); return
        if not self._require_browser(mutate=True):
            return
        try:
            value = self.app.owner.arm_direct_override(str(data.get("duration") or "")) if path.endswith("/arm") else self.app.owner.clear_direct_override()
            self._respond(200, value)
        except (ValueError, KeyError) as exc:
            self._respond(400, {"error": str(exc)})
        except Exception as exc:
            self.app.runtime.event("error", "web.direct_override_post_error", None, {"path": path, "error": str(exc)}); self._respond(500, {"error": "internal_error"})


def build_app(project_root: str | Path, owner_home: str | Path | None = None) -> WebApp:
    app = build_base_app(project_root, owner_home); sealer = Sealer.from_path(app.paths.signing_key); app.owner = OwnerOverrideStore(app.paths.owner_db, sealer.key); return app


def build_server(project_root: str | Path, owner_home: str | Path | None = None, host: str | None = None, port: int | None = None) -> ThreadingHTTPServer:
    app = build_app(project_root, owner_home); host = host or os.environ.get("ADS_WEB_HOST", "127.0.0.1"); port = int(os.environ.get("ADS_WEB_PORT", "8765") if port is None else port)
    handler = type("ConfiguredOwnerOverrideHandler", (OwnerOverrideHandler,), {"app": app}); return ThreadingHTTPServer((host, port), handler)
