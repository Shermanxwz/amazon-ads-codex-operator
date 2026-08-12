.PHONY: test archive-check preflight bootstrap web dry-run hourly daily weekly emergency-stop status
bootstrap:
	python3 scripts/bootstrap.py
web:
	python3 scripts/run_web.py
preflight:
	python3 scripts/preflight.py
test:
	python3 -m pytest -q
archive-check:
	python3 scripts/archive_check.py
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
