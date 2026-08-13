from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_full_stack_requires_owner_web_and_systemd_surface_acceptance():
    archive = (ROOT / ".github/workflows/archive.yml").read_text()
    surface = ROOT / "scripts/virtual_surface_acceptance.py"
    installer = (ROOT / "scripts/install_systemd.sh").read_text()
    assert surface.exists()
    assert "virtual_surface_acceptance.py --report virtual-surface-report.json" in archive
    assert "Owner Web and systemd production-surface acceptance" in archive
    assert "ADS_SYSTEMD_RENDER_ONLY" in installer
    assert "systemctl --user" in installer


def test_surface_acceptance_uses_production_entrypoints_and_security_flow():
    surface = (ROOT / "scripts/virtual_surface_acceptance.py").read_text()
    for token in (
        "scripts/run_web.py",
        "/api/login",
        "X-CSRF-Token",
        "/api/revisions/restore",
        "/api/mode",
        "/api/emergency-stop",
        "scripts/install_systemd.sh",
        "systemd-analyze",
        "owner-web-production-entrypoint",
        "systemd-render-install",
    ):
        assert token in surface
