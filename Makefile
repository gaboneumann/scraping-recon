.PHONY: test test-unit test-integration test-smoke update-snapshots

test:
	venv/bin/pytest tests/unit/ tests/integration/ -v --tb=short --cov=modules --cov=utils --cov-report=term-missing

test-unit:
	venv/bin/pytest tests/unit/ -v --tb=short

test-integration:
	venv/bin/pytest tests/integration/ -v --tb=short

test-smoke:
	venv/bin/pytest -m smoke -v --tb=short

update-snapshots:
	UPDATE_SNAPSHOTS=1 venv/bin/pytest -m smoke -v
