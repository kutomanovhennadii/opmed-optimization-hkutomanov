# Use poetry for all python commands
PYTHON ?= poetry run python
PKG = src/opmed

# Added gendata and tune-best here
.PHONY: setup lint test fmt precommit hooks tune tune-best run clean schemas check gendata

# Install dependencies
setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]
	pre-commit install

# Linters and static analysis
lint:
	poetry run pre-commit run --all-files || poetry run pre-commit run --all-files

# Formatting (auto-fix)
fmt:
	poetry run black .
	poetry run toml-sort pyproject.toml --in-place --all

# Run tests
test:
	poetry run pytest -q

# Pre-commit and linters
precommit:
	poetry run pre-commit run --all-files || poetry run pre-commit run --all-files

hooks:
	pre-commit install

# Generate JSON schemas
schemas:
	poetry run python -m scripts.gen_schemas

# Run the main pipeline
run:
	poetry run python -m scripts.run --config config/config.yaml --input data/input/synthetic_3d_8r.csv --output data/output

# --- Epic 7: Tuning (Task 7.3.4) ---

# Run hyperparameter tuning
tune:
	poetry run python -m scripts.tune

# Select the best config from the tuning run
tune-best:
	poetry run python -m scripts.select_best_config

# --- End Epic 7 ---

# Clean up cache files
clean:
	-rd /s /q .pytest_cache
	-rd /s /q .mypy_cache
	-rd /s /q .ruff_cache
	-del /f /q .coverage

# Comprehensive check (format, lint, test, hooks)
check: fmt lint test

.PHONY: gendata
gendata:
	poetry run python -m scripts.gen_synthetic_data
