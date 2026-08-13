.PHONY: install validate lint typecheck test run clean traceability \
	weather-contract schema-contract scientific-validation weather-integration weather-regression \
	operator-console-install operator-console-lint operator-console-typecheck \
	operator-console-test operator-console-check

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

weather-contract:
	pytest -q --no-cov \
		tests/unit/test_source_manifests.py \
		tests/unit/test_grid_assets.py \
		tests/unit/test_grib_index.py \
		tests/unit/test_gfs_manifest.py \
		tests/unit/test_eccodes_backend.py \
		tests/unit/test_cycle_lifecycle.py \
		tests/unit/test_coordinates.py \
		tests/unit/test_wind.py \
		tests/unit/test_vector_tiles.py \
		tests/contract/test_weather_schemas.py \
		tests/contract/test_weather_deployment_policy.py \
		tests/functional/test_weather_acquisition_cli.py

schema-contract:
	python scripts/validate_schemas.py
	pytest -q --no-cov \
		tests/contract/test_weather_schemas.py \
		tests/contract/test_weather_deployment_policy.py

scientific-validation:
	pytest -q --no-cov \
		tests/unit/test_probability.py \
		tests/unit/test_verification.py \
		tests/unit/test_grid_assets.py \
		tests/unit/test_gfs_manifest.py \
		tests/unit/test_eccodes_backend.py \
		tests/unit/test_cycle_lifecycle.py \
		tests/unit/test_coordinates.py \
		tests/unit/test_wind.py \
		tests/unit/test_vector_tiles.py \
		tests/regression/test_weather_adversarial_regressions.py

weather-integration:
	pytest -q --no-cov \
		tests/functional/test_weather_acquisition_cli.py \
		tests/integration/test_weather_vertical_slice.py \
		tests/regression/test_weather_adversarial_regressions.py

weather-regression:
	pytest -q --no-cov tests/regression/test_weather_adversarial_regressions.py

run:
	uvicorn weather_platform.api.main:app --host 127.0.0.1 --port 8080 --reload

traceability:
	python scripts/generate_traceability.py

operator-console-install:
	npm --prefix apps/operator-console ci

operator-console-lint:
	npm --prefix apps/operator-console run lint

operator-console-typecheck:
	npm --prefix apps/operator-console run typecheck

operator-console-test:
	npm --prefix apps/operator-console test

operator-console-check: operator-console-lint operator-console-typecheck operator-console-test

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov dist build *.egg-info
