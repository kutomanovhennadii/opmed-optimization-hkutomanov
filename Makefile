PYTHON ?= python
PKG = src/opmed

.PHONY: setup lint test fmt precommit hooks tune run clean schemas check

# Установка зависимостей
setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .[dev]
	pre-commit install

# Линтеры и статический анализ
lint:
	ruff check . --fix
	black --check .
	mypy src

# Форматирование (автоисправление)
fmt:
	poetry run black .
	poetry run toml-sort pyproject.toml --in-place --all

# Прогон тестов
test:
	pytest -q

# Предкоммит и линтеры
precommit:
	poetry run pre-commit run --all-files || poetry run pre-commit run --all-files


hooks:
	pre-commit install

# Генерация JSON-схем
schemas:
	$(PYTHON) scripts/gen_schemas.py

# Запуск основного пайплайна
run:
	$(PYTHON) scripts/run.py --config configs/config.yaml --surgeries data/input/surgeries.csv --outdir data/output

# Тюнинг гиперпараметров
tune:
	$(PYTHON) scripts/tune.py --config configs/config.yaml --grid configs/tune_grid.yaml --outdir data/output/tune

# Очистка мусора
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage

# Комплексная проверка (формат, линтер, тесты, хуки)
check: fmt lint test precommit
