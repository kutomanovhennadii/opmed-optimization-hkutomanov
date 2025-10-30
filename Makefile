PYTHON ?= python
PKG = src/opmed

.PHONY: setup lint test fmt check tune run clean

# Установка зависимостей
setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]
	pre-commit install

# Линтеры и статический анализ
lint:
	ruff check .
	black --check .
	mypy src

# Форматирование (автоисправление)
fmt:
	poetry run black .
	poetry run toml-sort pyproject.toml --in-place --all

# Прогон тестов
test:
	pytest -q

# Локальный предкоммит-чекер
check:
	$(PYTHON) scripts/local_check.py

# Запуск основного пайплайна
run:
	$(PYTHON) scripts/run.py --config configs/config.yaml --surgeries data/input/surgeries.csv --outdir data/output

# Тюнинг гиперпараметров
tune:
	$(PYTHON) scripts/tune.py --config configs/config.yaml --grid configs/tune_grid.yaml --outdir data/output/tune

# Очистка мусора
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage

.PHONY: precommit hooks

# Установка и запуск pre-commit
hooks:
	pre-commit install

precommit:
	pre-commit run --all-files

check: fmt lint test precommit
