from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .contract import canonical_json, contract_digest, load_contract

UTC = timezone.utc


def file_sha256(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run(binary: Path, args: list[str], *, env: dict[str, str] | None = None, timeout: int = 20) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            [str(binary), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            timeout=timeout,
            check=False,
        )
        return int(proc.returncode), proc.stdout or ""
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, f"{type(exc).__name__}: {exc}"


def _check(checks: list[dict[str, Any]], *, name: str, ok: bool, detail: str, required: bool = True) -> None:
    checks.append({"name": name, "ok": bool(ok), "required": bool(required), "detail": detail})


def _strict_config_smoke(binary: Path) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="codex-compat-") as temp_dir:
        home = Path(temp_dir)
        (home / "config.toml").write_text(
            "[features]\n"
            "hooks = true\n\n"
            "[mcp_servers.compat_probe]\n"
            "command = \"/bin/true\"\n"
            "enabled = false\n"
            "required = false\n"
            "startup_timeout_sec = 5\n"
            "tool_timeout_sec = 5\n"
            "default_tools_approval_mode = \"writes\"\n"
            "enabled_tools = [\"read\"]\n"
        )
        (home / "hooks.json").write_text(json.dumps({"hooks": {}}, separators=(",", ":")))
        env = dict(os.environ)
        env["CODEX_HOME"] = str(home)
        rc, output = _run(binary, ["exec", "--strict-config", "--help"], env=env)
        tail = output.strip().replace("\n", " ")[-500:]
        return rc == 0, tail or f"exit={rc}"


def probe_codex(binary: str | Path, contract_path: str | Path) -> dict[str, Any]:
    contract = load_contract(contract_path)
    source = Path(binary).expanduser()
    checks: list[dict[str, Any]] = []

    exists = source.exists()
    executable = exists and source.is_file() and os.access(source, os.X_OK)
    _check(checks, name="binary-executable", ok=executable, detail=str(source))
    if not executable:
        return _finalize(source, contract_path, checks, version="", binary_sha="")

    resolved = source.resolve()
    try:
        binary_sha = file_sha256(resolved)
        _check(checks, name="binary-sha256", ok=True, detail=binary_sha)
    except OSError as exc:
        binary_sha = ""
        _check(checks, name="binary-sha256", ok=False, detail=str(exc))

    rc, version_output = _run(resolved, ["--version"])
    version = version_output.strip().splitlines()[0] if version_output.strip() else ""
    _check(checks, name="version", ok=rc == 0 and bool(version), detail=version or f"exit={rc}")

    for command in contract.get("required_commands", []):
        name = str(command["name"])
        rc, output = _run(resolved, [str(x) for x in command["argv"]])
        _check(checks, name=f"command:{name}", ok=rc == 0, detail=(output.strip()[-500:] or f"exit={rc}"))
        if rc == 0:
            for token in command.get("required_tokens") or []:
                _check(
                    checks,
                    name=f"command:{name}:token:{token}",
                    ok=str(token) in output,
                    detail=f"required token {token}",
                )

    if contract.get("strict_config_smoke", False):
        ok, detail = _strict_config_smoke(resolved)
        _check(checks, name="strict-config-smoke", ok=ok, detail=detail)

    return _finalize(resolved, contract_path, checks, version=version, binary_sha=binary_sha)


def _finalize(binary: Path, contract_path: str | Path, checks: list[dict[str, Any]], *, version: str, binary_sha: str) -> dict[str, Any]:
    compatible = all(item["ok"] for item in checks if item.get("required", True))
    core = {
        "binary": str(binary),
        "binary_sha256": binary_sha,
        "version_text": version,
        "contract_sha256": contract_digest(contract_path),
        "compatible": compatible,
        "checks": checks,
    }
    core["probe_digest"] = hashlib.sha256(canonical_json(core).encode()).hexdigest()
    core["probed_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return core
