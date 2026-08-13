.PHONY: test archive-check virtual-acceptance codex-compat codex-runtime-status codex-adopt codex-rollback preflight bootstrap web dry-run hourly daily weekly emergency-stop status optimization-report backup

bootstrap:
	python3 scripts/bootstrap.py

web:
	python3 scripts/run_web.py

codex-compat:
	python3 scripts/check_codex_runtime.py

codex-runtime-status:
	python3 scripts/codex_runtime.py status

codex-adopt:
	python3 scripts/codex_runtime.py adopt-current

codex-rollback:
	python3 scripts/codex_runtime.py rollback

preflight:
	python3 scripts/preflight.py

test:
	python3 -m pytest -q

archive-check:
	python3 scripts/archive_check.py

virtual-acceptance:
	python3 scripts/virtual_acceptance.py --report virtual-acceptance-report.json
	python3 scripts/virtual_surface_acceptance.py --report virtual-surface-report.json

dry-run:
	python3 scripts/run_cycle.py daily --dry-run

hourly:
	python3 scripts/run_cycle.py hourly

daily:
	python3 scripts/run_cycle.py daily

weekly:
	python3 scripts/run_cycle.py weekly

emergency-stop:
	python3 scripts/ownerctl.py emergency-stop

status:
	python3 scripts/ownerctl.py status

optimization-report:
	python3 scripts/optimization_report.py

backup:
	python3 scripts/backup_owner.py
