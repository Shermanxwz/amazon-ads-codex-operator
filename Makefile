.PHONY: test preflight dry-run bootstrap hourly daily weekly
bootstrap:
	python3 scripts/bootstrap.py
preflight:
	python3 scripts/preflight.py
test:
	python3 -m pytest -q
dry-run:
	python3 scripts/run_cycle.py daily --dry-run
hourly:
	python3 scripts/run_cycle.py hourly
daily:
	python3 scripts/run_cycle.py daily
weekly:
	python3 scripts/run_cycle.py weekly
