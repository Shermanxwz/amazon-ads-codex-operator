from pathlib import Path

from ads_autopilot.codex_runner import build_command, sanitized_env
from ads_autopilot.paths import RuntimePaths


def test_codex_command_is_read_only_and_role_gated(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ADS_DEV_ALLOW_PATH_CODEX", "1")
    project = tmp_path / "project"
    project.mkdir()
    owner = tmp_path / "owner"
    paths = RuntimePaths.resolve(project, owner)
    paths.ensure_directories()
    executor = paths.workspace_root / "executor-test"
    executor.mkdir()
    cmd = build_command(paths=paths, workspace=executor, schema=project / "schema.json", output=paths.run_root / "out.json")
    assert cmd[0] == "codex"
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("--ask-for-approval") + 1] == "never"
    assert "--json" in cmd
    assert any('default_tools_approval_mode="approve"' in item for item in cmd)
    planner = paths.workspace_root / "planner-test"
    planner.mkdir()
    pcmd = build_command(paths=paths, workspace=planner, schema=project / "schema.json", output=paths.run_root / "p.json")
    assert any('default_tools_approval_mode="writes"' in item for item in pcmd)


def test_production_runner_refuses_unpinned_path_codex(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("ADS_DEV_ALLOW_PATH_CODEX", raising=False)
    project = tmp_path / "project"
    project.mkdir()
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()
    workspace = paths.workspace_root / "planner-test"
    workspace.mkdir()
    try:
        build_command(paths=paths, workspace=workspace, schema=project / "schema.json", output=paths.run_root / "p.json")
    except Exception as exc:
        assert "ACTIVE" in str(exc)
    else:
        raise AssertionError("production runner silently fell back to PATH Codex")


def test_codex_environment_does_not_forward_owner_secrets(tmp_path: Path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    paths = RuntimePaths.resolve(project, tmp_path / "owner")
    paths.ensure_directories()
    workspace = paths.workspace_root / "planner-test"
    workspace.mkdir()
    monkeypatch.setenv("ADS_OPERATOR_SIGNING_KEY", "secret")
    monkeypatch.setenv("AMAZON_ADS_CLIENT_SECRET", "secret2")
    monkeypatch.setenv("SOME_UNRELATED_SECRET", "secret3")
    env = sanitized_env(paths, workspace)
    assert "ADS_OPERATOR_SIGNING_KEY" not in env
    assert "AMAZON_ADS_CLIENT_SECRET" not in env
    assert "SOME_UNRELATED_SECRET" not in env
    assert env["CODEX_HOME"] == str(paths.codex_home)
    assert Path(env["HOME"]).is_relative_to(workspace)
