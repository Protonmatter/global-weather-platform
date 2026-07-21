.PHONY: install validate lint typecheck test run clean traceability

install:
	python -m pip install -e '.[dev]'

validate:
	python scripts/validate_specs.py
	python scripts/validate_schemas.py
	python scripts/generate_traceability.py --check

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy

test:
	pytest

run:
	uvicorn weather_platform.api.main:app --host 127.0.0.1 --port 8080 --reload

traceability:
	python scripts/generate_traceability.py

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info
