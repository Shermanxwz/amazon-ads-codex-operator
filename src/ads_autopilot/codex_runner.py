from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time
import uuid
from typing import Any

from .canonical import canonical_json
from .codex_compat import active_identity, resolve_active_binary
from .paths import RuntimePaths


class CodexError(RuntimeError):
    pass


_ENV_ALLOW = {
    "PATH",
    "LANG",
    "LANGUAGE",
    "LC_ALL",
    "LC_CTYPE",
    "TERM",
    "COLORTERM",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
}


def sanitized_env(
    paths: RuntimePaths,
    workspace: Path,
    *,
    role: str = "read_only",
    grant_path: Path | None = None,
) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW or k.startswith("LC_")}
    fake_home = workspace / "home"
    fake_home.mkdir(parents=True, exist_ok=True, mode=0o700)
    env["HOME"] = str(fake_home)
    env["CODEX_HOME"] = str(paths.codex_home)
    env["PYTHONUNBUFFERED"] = "1"
    env["ADS_CODEX_HOOK_MODE"] = "executor" if role == "executor" else "read_only"
    if grant_path is not None:
        env["ADS_CODEX_EXEC_GRANT"] = str(grant_path)
    return env


def prepare_workspace(paths: RuntimePaths, role: str) -> Path:
    paths.ensure_directories()
    workspace = paths.workspace_root / f"{role}-{uuid.uuid4().hex}"
    workspace.mkdir(parents=True, mode=0o700)
    constitution = paths.project_root / "AGENTS.md"
    if constitution.exists():
        shutil.copy2(constitution, workspace / "AGENTS.md")
    (workspace / "WORKSPACE_NOTICE.txt").write_text(
        "Disposable Codex workspace. Owner policy, signing keys, OAuth config, and runtime DB live outside this directory.\n"
    )
    return workspace


def build_command(
    *,
    paths: RuntimePaths,
    workspace: Path,
    schema: Path,
    output: Path,
    model: str | None = None,
    allowed_mcp_tools: list[str] | None = None,
) -> list[str]:
    codex_binary = resolve_active_binary(
        paths, allow_path_fallback=os.environ.get("ADS_DEV_ALLOW_PATH_CODEX") == "1"
    )
    cmd = [
        codex_binary,
        "exec",
        "--cd",
        str(workspace),
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--strict-config",
        "--dangerously-bypass-hook-trust",
        "--ephemeral",
        "--json",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(output),
        "--config",
        'approval_policy="never"',
    ]
    approval = "approve" if workspace.name.startswith("executor-") else "writes"
    cmd.extend(
        [
            "--config",
            f'mcp_servers.amazon_ads.default_tools_approval_mode="{approval}"',
        ]
    )
    if allowed_mcp_tools is not None:
        encoded = json.dumps([str(x) for x in allowed_mcp_tools], separators=(",", ":"))
        cmd.extend(["--config", f"mcp_servers.amazon_ads.enabled_tools={encoded}"])
    if model:
        cmd.extend(["--model", model])
    cmd.append("-")
    return cmd


def _verification_grace_seconds(paths: RuntimePaths) -> float:
    try:
        with sqlite3.connect(paths.owner_db, timeout=2) as conn:
            row = conn.execute(
                "SELECT body_json FROM owner_documents WHERE kind='policy'"
            ).fetchone()
        if not row:
            return 0.0
        policy = json.loads(row[0] or "{}")
        return min(
            3600.0,
            max(0.0, float(policy.get("recovery", {}).get("verification_grace_seconds") or 0)),
        )
    except Exception:
        return 0.0


def _prompt_payload(prompt: str) -> dict[str, Any]:
    marker = "INPUT_JSON:\n"
    if marker not in prompt:
        return {}
    try:
        value = json.loads(prompt.rsplit(marker, 1)[1])
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _scalar_equal(expected: Any, observed: Any) -> bool:
    if isinstance(expected, bool) or isinstance(observed, bool):
        return expected is observed
    if expected == observed:
        return True
    try:
        left, right = float(expected), float(observed)
    except (TypeError, ValueError):
        return False
    return abs(left - right) <= max(1e-9, abs(left) * 1e-9, abs(right) * 1e-9)


def _state_differences(expected: Any, observed: Any, path: str = "state") -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return [f"{path}: expected object, observed {type(observed).__name__}"]
        differences: list[str] = []
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in observed:
                differences.append(f"{child}: missing from fresh observation")
            else:
                differences.extend(_state_differences(expected_value, observed[key], child))
        return differences
    if isinstance(expected, list):
        if not isinstance(observed, list):
            return [f"{path}: expected list, observed {type(observed).__name__}"]
        left = sorted(canonical_json(item) for item in expected)
        right = sorted(canonical_json(item) for item in observed)
        return [] if left == right else [f"{path}: list changed"]
    return [] if _scalar_equal(expected, observed) else [
        f"{path}: expected {expected!r}, observed {observed!r}"
    ]


def _enforce_verification(
    role: str, prompt: str, value: Any
) -> tuple[dict[str, Any], bool]:
    if not isinstance(value, dict):
        raise CodexError("verifier structured output is not an object")
    if role not in {"verifier", "state_verifier"}:
        return value, True

    payload = _prompt_payload(prompt)
    if role == "state_verifier":
        expected = payload.get("expected_state") or {}
        expected_hash = str(payload.get("action_hash") or "")
    else:
        sealed = payload.get("sealed_actions") or []
        action = sealed[0] if isinstance(sealed, list) and len(sealed) == 1 and isinstance(sealed[0], dict) else {}
        expected = action.get("after") or {}
        expected_hash = str(action.get("action_hash") or "")

    if not isinstance(expected, dict) or not expected:
        raise CodexError("verifier has no non-empty sealed expected state")
    results = value.get("results")
    if not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        raise CodexError("verifier must return exactly one structured result")
    item = dict(results[0])
    if expected_hash and str(item.get("action_hash") or "") != expected_hash:
        raise CodexError("verifier returned wrong/missing action_hash")
    observed = item.get("observed") or {}
    deterministic = _state_differences(expected, observed)
    model_differences = [str(x) for x in (item.get("differences") or [])]
    differences = list(dict.fromkeys(model_differences + deterministic))

    # Model judgment can never promote a deterministic mismatch to VERIFIED.
    # A model-declared mismatch is also not silently promoted merely because a
    # subset happens to compare equal; the fresh reader must explicitly agree.
    verified = str(item.get("status") or "") == "verified" and not deterministic
    if not verified and str(item.get("status") or "") == "verified":
        item["status"] = "mismatch"
    item["differences"] = differences
    value = dict(value)
    value["results"] = [item]
    return value, verified


def run_codex(
    *,
    paths: RuntimePaths,
    role: str,
    prompt: str,
    schema: Path,
    output: Path,
    timeout: int = 1800,
    model: str | None = None,
    keep_workspace: bool = False,
    grant_path: Path | None = None,
    allowed_mcp_tools: list[str] | None = None,
) -> dict[str, Any]:
    workspace = prepare_workspace(paths, role)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    cmd = build_command(
        paths=paths,
        workspace=workspace,
        schema=schema,
        output=output,
        model=model,
        allowed_mcp_tools=allowed_mcp_tools,
    )
    identity = active_identity(paths)
    runtime_evidence = {
        "selected_binary": cmd[0],
        "selection": "owner-pinned-active" if identity is not None else "PATH-fallback-unsealed",
        "runtime": identity,
    }
    runtime_log = output.with_name(output.name + ".runtime.json")
    runtime_log.write_text(json.dumps(runtime_evidence, indent=2, sort_keys=True))
    os.chmod(runtime_log, 0o600)

    grace = _verification_grace_seconds(paths) if role == "verifier" else 0.0
    deadline = time.monotonic() + grace
    attempt = 0
    last_error: Exception | None = None
    try:
        while True:
            attempt += 1
            output.unlink(missing_ok=True)
            try:
                proc = subprocess.run(
                    cmd,
                    input=prompt,
                    text=True,
                    cwd=workspace,
                    env=sanitized_env(paths, workspace, role=role, grant_path=grant_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=timeout,
                )
                suffix = "" if attempt == 1 else f".attempt-{attempt}"
                event_log = output.with_name(output.name + suffix + ".events.jsonl")
                event_log.write_text(proc.stdout or "")
                os.chmod(event_log, 0o600)
                if proc.stderr:
                    stderr_log = output.with_name(output.name + suffix + ".stderr.log")
                    stderr_log.write_text(proc.stderr)
                    os.chmod(stderr_log, 0o600)
                if proc.returncode != 0:
                    raise CodexError(
                        f"codex exec failed ({proc.returncode}): {proc.stderr[-4000:]}"
                    )
                if not output.exists():
                    raise CodexError("codex did not write structured output")
                try:
                    raw = json.loads(output.read_text())
                except Exception as exc:
                    raise CodexError(f"invalid structured output: {exc}") from exc
                value, verified = _enforce_verification(role, prompt, raw)
                if role in {"verifier", "state_verifier"}:
                    output.write_text(json.dumps(value, indent=2, sort_keys=True))
                    os.chmod(output, 0o600)
                if role != "verifier" or verified:
                    return value
                last_error = CodexError("post-write state is not yet deterministically verified")
            except Exception as exc:
                last_error = exc
                if role != "verifier":
                    raise

            if time.monotonic() >= deadline:
                if isinstance(last_error, CodexError) and output.exists():
                    try:
                        return json.loads(output.read_text())
                    except Exception:
                        pass
                assert last_error is not None
                raise last_error
            time.sleep(min(2.0, max(0.05, deadline - time.monotonic())))
    finally:
        if not keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)
