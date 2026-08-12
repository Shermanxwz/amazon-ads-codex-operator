from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterator

from ads_autopilot.paths import RuntimePaths
from .probe import file_sha256, probe_codex

UTC = timezone.utc
REGISTRY_VERSION = 1


class CodexRuntimeError(RuntimeError):
    pass


def runtime_root(paths: RuntimePaths) -> Path:
    return paths.owner_home / "codex-runtimes"


def registry_path(paths: RuntimePaths) -> Path:
    return runtime_root(paths) / "registry.json"


def slots_root(paths: RuntimePaths) -> Path:
    return runtime_root(paths) / "slots"


def lock_path(paths: RuntimePaths) -> Path:
    return runtime_root(paths) / "registry.lock"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _ensure(paths: RuntimePaths) -> None:
    for path in (runtime_root(paths), slots_root(paths)):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            path.chmod(0o700)
        except OSError:
            pass


@contextmanager
def _exclusive_registry(paths: RuntimePaths) -> Iterator[None]:
    _ensure(paths)
    path = lock_path(paths)
    with path.open("a+") as handle:
        try:
            path.chmod(0o600)
        except OSError:
            pass
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _empty_registry() -> dict[str, Any]:
    return {"version": REGISTRY_VERSION, "active": None, "previous": None, "candidates": {}, "history": []}


def _validate_registry(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or int(value.get("version") or 0) != REGISTRY_VERSION:
        raise CodexRuntimeError("unsupported or invalid Codex runtime registry")
    if value.get("active") is not None and not isinstance(value.get("active"), dict):
        raise CodexRuntimeError("invalid active Codex runtime record")
    if value.get("previous") is not None and not isinstance(value.get("previous"), dict):
        raise CodexRuntimeError("invalid previous Codex runtime record")
    if not isinstance(value.get("candidates", {}), dict) or not isinstance(value.get("history", []), list):
        raise CodexRuntimeError("invalid Codex runtime registry collections")
    value.setdefault("active", None)
    value.setdefault("previous", None)
    value.setdefault("candidates", {})
    value.setdefault("history", [])
    return value


def load_registry(paths: RuntimePaths) -> dict[str, Any]:
    _ensure(paths)
    path = registry_path(paths)
    if not path.exists():
        return _empty_registry()
    try:
        value = json.loads(path.read_text())
    except Exception as exc:
        raise CodexRuntimeError(f"cannot parse Codex runtime registry: {exc}") from exc
    return _validate_registry(value)


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def save_registry(paths: RuntimePaths, value: dict[str, Any]) -> None:
    _validate_registry(value)
    _ensure(paths)
    destination = registry_path(paths)
    fd, temp_name = tempfile.mkstemp(prefix="registry-", suffix=".json", dir=str(destination.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, destination)
        _fsync_dir(destination.parent)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _verify_record(record: dict[str, Any]) -> tuple[bool, str]:
    path = Path(str(record.get("binary") or ""))
    expected = str(record.get("binary_sha256") or "")
    if not path.is_file() or not os.access(path, os.X_OK):
        return False, f"runtime binary missing/not executable: {path}"
    try:
        actual = file_sha256(path)
    except OSError as exc:
        return False, str(exc)
    if not expected or actual != expected:
        return False, f"runtime fingerprint mismatch: expected={expected} actual={actual}"
    return True, actual


def register_candidate(paths: RuntimePaths, binary: str | Path, contract_path: str | Path) -> dict[str, Any]:
    _ensure(paths)
    source = Path(binary).expanduser().resolve()
    if not source.is_file() or not os.access(source, os.X_OK):
        raise CodexRuntimeError(f"candidate Codex is not an executable file: {source}")
    source_sha = file_sha256(source)
    slot = slots_root(paths) / source_sha
    slot.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = slot / "codex"
    if not target.exists():
        temp = slot / f".codex-{os.getpid()}.tmp"
        shutil.copy2(source, temp)
        temp.chmod(0o500)
        with temp.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temp, target)
        _fsync_dir(slot)
    try:
        target.chmod(0o500)
    except OSError:
        pass
    if file_sha256(target) != source_sha:
        raise CodexRuntimeError("candidate snapshot hash mismatch")

    # Probe the copied slot, not the source path. A launcher that depends on
    # files outside its snapshot will fail here and can never be promoted.
    probe = probe_codex(target, contract_path)
    record = {
        "id": source_sha,
        "source_binary": str(source),
        "binary": str(target),
        "binary_sha256": source_sha,
        "version_text": probe.get("version_text", ""),
        "contract_sha256": probe.get("contract_sha256", ""),
        "probe_digest": probe.get("probe_digest", ""),
        "compatible": bool(probe.get("compatible")),
        "registered_at": _now(),
        "probe": probe,
    }
    with _exclusive_registry(paths):
        registry = load_registry(paths)
        registry["candidates"][source_sha] = record
        registry["history"].append({"event": "candidate_registered", "runtime_id": source_sha, "at": _now(), "compatible": record["compatible"]})
        registry["history"] = registry["history"][-100:]
        save_registry(paths, registry)
    return record


def promote_candidate(paths: RuntimePaths, runtime_id: str, contract_path: str | Path) -> dict[str, Any]:
    with _exclusive_registry(paths):
        registry = load_registry(paths)
        record = registry.get("candidates", {}).get(runtime_id)
        if not isinstance(record, dict):
            raise CodexRuntimeError(f"unknown Codex runtime candidate: {runtime_id}")
        ok, detail = _verify_record(record)
        if not ok:
            raise CodexRuntimeError(detail)
        fresh_probe = probe_codex(record["binary"], contract_path)
        if not fresh_probe.get("compatible"):
            raise CodexRuntimeError("candidate no longer satisfies the Codex capability contract")
        old_active = registry.get("active")
        promoted = dict(record)
        promoted["probe"] = fresh_probe
        promoted["probe_digest"] = fresh_probe["probe_digest"]
        promoted["contract_sha256"] = fresh_probe["contract_sha256"]
        promoted["promoted_at"] = _now()
        registry["previous"] = old_active
        registry["active"] = promoted
        registry["candidates"][runtime_id] = promoted
        registry["history"].append({"event": "promoted", "runtime_id": runtime_id, "previous_runtime_id": (old_active or {}).get("id") if isinstance(old_active, dict) else None, "at": _now()})
        registry["history"] = registry["history"][-100:]
        save_registry(paths, registry)
        return promoted


def rollback_runtime(paths: RuntimePaths, contract_path: str | Path) -> dict[str, Any]:
    with _exclusive_registry(paths):
        registry = load_registry(paths)
        previous = registry.get("previous")
        if not isinstance(previous, dict):
            raise CodexRuntimeError("no previous Codex runtime is available for rollback")
        ok, detail = _verify_record(previous)
        if not ok:
            raise CodexRuntimeError(detail)
        probe = probe_codex(previous["binary"], contract_path)
        if not probe.get("compatible"):
            raise CodexRuntimeError("previous Codex runtime no longer satisfies the current capability contract")
        current = registry.get("active")
        restored = dict(previous)
        restored["probe"] = probe
        restored["probe_digest"] = probe["probe_digest"]
        restored["contract_sha256"] = probe["contract_sha256"]
        restored["promoted_at"] = _now()
        registry["active"] = restored
        registry["previous"] = current
        registry["history"].append({"event": "rollback", "runtime_id": restored.get("id"), "replaced_runtime_id": (current or {}).get("id") if isinstance(current, dict) else None, "at": _now()})
        registry["history"] = registry["history"][-100:]
        save_registry(paths, registry)
        return restored


def active_identity(paths: RuntimePaths) -> dict[str, Any] | None:
    registry = load_registry(paths)
    active = registry.get("active")
    if not isinstance(active, dict):
        return None
    ok, detail = _verify_record(active)
    result = dict(active)
    result["integrity_ok"] = ok
    result["integrity_detail"] = detail
    return result


def resolve_active_binary(paths: RuntimePaths, *, allow_path_fallback: bool = True) -> str:
    identity = active_identity(paths)
    if identity is not None:
        if not identity.get("integrity_ok"):
            raise CodexRuntimeError(str(identity.get("integrity_detail") or "active Codex runtime integrity failed"))
        return str(identity["binary"])
    if allow_path_fallback:
        return shutil.which("codex") or "codex"
    raise CodexRuntimeError("no Owner-pinned ACTIVE Codex runtime configured")


def runtime_status(paths: RuntimePaths) -> dict[str, Any]:
    registry = load_registry(paths)
    active = registry.get("active")
    previous = registry.get("previous")
    active_ok, active_detail = _verify_record(active) if isinstance(active, dict) else (False, "not configured")
    previous_ok, previous_detail = _verify_record(previous) if isinstance(previous, dict) else (False, "not configured")
    return {
        "registry": str(registry_path(paths)),
        "active": active,
        "active_integrity_ok": active_ok,
        "active_integrity_detail": active_detail,
        "previous": previous,
        "previous_integrity_ok": previous_ok if previous is not None else None,
        "previous_integrity_detail": previous_detail,
        "candidate_count": len(registry.get("candidates", {})),
        "history": registry.get("history", [])[-20:],
    }
