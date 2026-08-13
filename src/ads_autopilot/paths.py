from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OWNER_HOME = Path.home() / ".local" / "share" / "amazon-ads-codex-owner"


@dataclass(frozen=True)
class RuntimePaths:
    project_root: Path
    owner_home: Path
    owner_db: Path
    runtime_db: Path
    signing_key: Path
    grant_signing_key: Path
    codex_home: Path
    run_root: Path
    workspace_root: Path
    grant_root: Path
    trusted_hook_root: Path
    trusted_hook_file: Path
    lock_file: Path

    @classmethod
    def resolve(cls, project_root: str | Path, owner_home: str | Path | None = None) -> "RuntimePaths":
        project = Path(project_root).resolve()
        explicit = owner_home or os.environ.get("ADS_OWNER_HOME")
        home = Path(explicit).expanduser().resolve() if explicit else DEFAULT_OWNER_HOME.expanduser().resolve()
        return cls(
            project_root=project,
            owner_home=home,
            owner_db=home / "owner.db",
            runtime_db=home / "runtime.db",
            signing_key=home / "secrets" / "operator_signing_key",
            grant_signing_key=home / "secrets" / "executor_grant_signing_key",
            codex_home=home / "codex-home",
            run_root=home / "runs",
            workspace_root=home / "codex-workspaces",
            grant_root=home / "grants",
            trusted_hook_root=home / "trusted-hooks",
            trusted_hook_file=home / "trusted-hooks" / "codex_pretool_hook.py",
            lock_file=home / "operator.lock",
        )

    def ensure_directories(self) -> None:
        self.owner_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in (
            self.signing_key.parent,
            self.codex_home,
            self.run_root,
            self.workspace_root,
            self.grant_root,
            self.trusted_hook_root,
        ):
            path.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in (self.owner_home, self.signing_key.parent, self.codex_home, self.run_root, self.workspace_root, self.grant_root, self.trusted_hook_root):
            try:
                path.chmod(0o700)
            except OSError:
                pass
