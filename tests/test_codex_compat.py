from __future__ import annotations

import json
from pathlib import Path

from ads_autopilot.codex_compat import (
    active_identity,
    probe_codex,
    promote_candidate,
    register_candidate,
    resolve_active_binary,
    rollback_runtime,
)
from ads_autopilot.paths import RuntimePaths


def fake_codex(path: Path, version: str, *, omit: str = "") -> Path:
    tokens = "--strict-config --sandbox --ask-for-approval --dangerously-bypass-hook-trust --ephemeral --json --output-schema --output-last-message --config --model"
    script = f'''#!/bin/sh
set -eu
if [ "${{1:-}}" = "--version" ]; then echo "codex-cli {version}"; exit 0; fi
case "${{1:-}}" in
  exec) echo "{tokens.replace(omit, '')}" ;;
  mcp) echo "list login" ;;
  plugin)
    if [ "${{2:-}}" = "marketplace" ]; then echo "add list upgrade remove"; else echo "list marketplace"; fi ;;
  features) echo "list" ;;
  sandbox) echo "sandbox" ;;
  doctor) echo "doctor" ;;
  update) echo "update" ;;
  *) echo "unknown"; exit 2 ;;
esac
'''
    path.write_text(script)
    path.chmod(0o755)
    return path


def contract(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "config" / "codex-compatibility.json"
    target = tmp_path / "contract.json"
    target.write_text(source.read_text())
    return target


def test_probe_is_capability_based(tmp_path: Path):
    binary = fake_codex(tmp_path / "codex", "999.0")
    report = probe_codex(binary, contract(tmp_path))
    assert report["compatible"] is True
    assert report["version_text"] == "codex-cli 999.0"
    assert len(report["binary_sha256"]) == 64


def test_probe_rejects_missing_stable_flag(tmp_path: Path):
    binary = fake_codex(tmp_path / "codex", "999.1", omit="--output-schema")
    report = probe_codex(binary, contract(tmp_path))
    assert report["compatible"] is False
    assert any(item["name"].endswith("--output-schema") and not item["ok"] for item in report["checks"])


def test_active_runtime_is_snapshot_and_path_update_does_not_change_production(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "config").mkdir()
    contract_path = contract(project)
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()

    system = fake_codex(tmp_path / "system-codex", "1.0")
    first = register_candidate(paths, system, contract_path)
    assert first["compatible"] is True
    active = promote_candidate(paths, first["id"], contract_path)
    active_binary = Path(active["binary"])
    assert active_binary != system.resolve()
    assert resolve_active_binary(paths, allow_path_fallback=False) == str(active_binary)

    fake_codex(system, "2.0")
    assert resolve_active_binary(paths, allow_path_fallback=False) == str(active_binary)
    assert active_identity(paths)["version_text"] == "codex-cli 1.0"


def test_candidate_promote_and_rollback_are_atomic_registry_transitions(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    contract_path = contract(project)
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()

    one = register_candidate(paths, fake_codex(tmp_path / "codex-one", "1.0"), contract_path)
    promote_candidate(paths, one["id"], contract_path)
    two = register_candidate(paths, fake_codex(tmp_path / "codex-two", "2.0"), contract_path)
    promote_candidate(paths, two["id"], contract_path)
    assert active_identity(paths)["version_text"] == "codex-cli 2.0"
    restored = rollback_runtime(paths, contract_path)
    assert restored["version_text"] == "codex-cli 1.0"
    assert active_identity(paths)["version_text"] == "codex-cli 1.0"


def test_incompatible_candidate_cannot_be_promoted(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    contract_path = contract(project)
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()
    bad = register_candidate(paths, fake_codex(tmp_path / "bad", "3.0", omit="--json"), contract_path)
    assert bad["compatible"] is False
    try:
        promote_candidate(paths, bad["id"], contract_path)
    except Exception as exc:
        assert "capability contract" in str(exc)
    else:
        raise AssertionError("incompatible candidate was promoted")


def test_runner_uses_promoted_snapshot_not_path_binary(tmp_path: Path, monkeypatch):
    from ads_autopilot.codex_runner import build_command

    project = tmp_path / "project"
    project.mkdir()
    contract_path = contract(project)
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()
    candidate = register_candidate(paths, fake_codex(tmp_path / "system-codex", "7.0"), contract_path)
    active = promote_candidate(paths, candidate["id"], contract_path)
    monkeypatch.delenv("ADS_DEV_ALLOW_PATH_CODEX", raising=False)
    workspace = paths.workspace_root / "planner-test"
    workspace.mkdir()
    cmd = build_command(paths=paths, workspace=workspace, schema=project / "schema.json", output=paths.run_root / "out.json")
    assert cmd[0] == active["binary"]
