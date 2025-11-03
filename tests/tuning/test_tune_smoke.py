# tests/tuning/test_tune_smoke.py
"""
Тесты для скрипта scripts/tune.py (Эпик 7, Задача 7.3.2).

Тестируем логику оркестратора (генерация конфигов, вызов, сбор метрик),
но "мокаем" (mock) тяжелый вызов `run_pipeline`, чтобы
тесты проходили мгновенно.
"""

import csv
import json

import pytest
import yaml

# --- Функции, которые мы импортируем из нашего скрипта ---
# (Предполагаем, что tests/ находится на одном уровне с scripts/
#  и 'src' добавлена в PYTHONPATH)
from scripts.tune import (
    apply_run_config,
    generate_combinations,
    get_metrics_from_file,
    set_nested_key,
)
from scripts.tune import (
    main as tune_main,  # Импортируем main под псевдонимом
)

# --- Модульные тесты для хелперов ---


def test_set_nested_key():
    """Тестируем утилиту для установки вложенных ключей."""
    d = {}
    set_nested_key(d, "solver.num_workers", 8)
    assert d == {"solver": {"num_workers": 8}}

    set_nested_key(d, "solver.random_seed", 42)
    assert d == {"solver": {"num_workers": 8, "random_seed": 42}}

    set_nested_key(d, "activation_penalty", 10)
    assert d == {"solver": {"num_workers": 8, "random_seed": 42}, "activation_penalty": 10}


def test_generate_combinations():
    """Тестируем генератор декартова произведения."""
    tune_cfg = {
        "model": {"grid": {"activation_penalty": [1, 5]}},
        "solver": {
            "grid": {"search_branching": ["AUTOMATIC", "PORTFOLIO"], "linearization_level": [0]}
        },
    }

    combos = generate_combinations(tune_cfg)

    # Ожидаем 2 * 2 * 1 = 4 комбинации
    assert len(combos) == 4

    # Проверяем, что ключи правильно "расплющены"
    expected_combos = [
        {
            "activation_penalty": 1,
            "solver.search_branching": "AUTOMATIC",
            "solver.linearization_level": 0,
        },
        {
            "activation_penalty": 1,
            "solver.search_branching": "PORTFOLIO",
            "solver.linearization_level": 0,
        },
        {
            "activation_penalty": 5,
            "solver.search_branching": "AUTOMATIC",
            "solver.linearization_level": 0,
        },
        {
            "activation_penalty": 5,
            "solver.search_branching": "PORTFOLIO",
            "solver.linearization_level": 0,
        },
    ]

    # Сравниваем как множества, т.к. порядок не гарантирован
    expected_set = {tuple(sorted(d.items())) for d in expected_combos}
    actual_set = {tuple(sorted(d.items())) for d in combos}

    assert actual_set == expected_set


def test_apply_run_config(tmp_path):
    """Тестируем создание и сохранение временного конфига."""
    base_cfg = {"solver": {"random_seed": 0}, "buffer": 0.25}
    context = {"solver.max_time_in_seconds": 60, "buffer": 0.5}  # Контекст перекрывает buffer
    combo = {"solver.random_seed": 42, "activation_penalty": 10}
    run_output_dir = tmp_path

    config_path = apply_run_config(base_cfg, context, combo, run_output_dir)

    assert config_path == run_output_dir / "config_run.yaml"
    assert config_path.exists()

    # Загружаем и проверяем
    saved_cfg = yaml.safe_load(config_path.read_text())

    # 1. 'combo' (seed: 42) перекрыл 'base' (seed: 0)
    assert saved_cfg["solver"]["random_seed"] == 42
    # 2. 'context' (buffer: 0.5) перекрыл 'base' (buffer: 0.25)
    assert saved_cfg["buffer"] == 0.5
    # 3. 'context' (time_limit) добавился
    assert saved_cfg["solver"]["max_time_in_seconds"] == 60
    # 4. 'combo' (penalty) добавился
    assert saved_cfg["activation_penalty"] == 10
    # 5. output_dir был принудительно установлен
    assert saved_cfg["output_dir"] == str(run_output_dir)
    # 6. Ключи для сохранения артефактов включены
    assert saved_cfg["metrics"]["save_metrics"] is True
    assert saved_cfg["validation"]["write_report"] is True


def test_get_metrics_from_file(tmp_path):
    """Тестируем безопасное чтение metrics.json."""
    metrics_path = tmp_path / "metrics.json"

    # Случай 1: Файл не найден
    assert get_metrics_from_file(None) == {}
    assert get_metrics_from_file(metrics_path) == {}

    # Случай 2: Файл существует и валиден
    metrics_data = {
        "utilization": 0.85,
        "total_cost": 1500,
        "num_anesthetists": 5,
        "other_key": "ignore",
    }
    metrics_path.write_text(json.dumps(metrics_data))

    expected = {
        "utilization": 0.85,
        "total_cost": 1500,
        "num_anesthetists": 5,
        "num_rooms_used": None,  # .get() возвращает None, если ключа нет
    }
    assert get_metrics_from_file(metrics_path) == expected

    # Случай 3: Файл испорчен (не JSON)
    metrics_path.write_text("not valid json")
    assert get_metrics_from_file(metrics_path) == {}


# --- Дымовой тест для main() ---


@pytest.fixture
def mock_fs(tmp_path, monkeypatch):
    """
    Создает полную мок-файловую систему для тюнера в tmp_path
    и патчит константы путей в скрипте tune.py.
    """
    # 1. Создаем директории
    mock_configs_dir = tmp_path / "configs"
    mock_data_input_dir = tmp_path / "data" / "input"
    mock_data_output_tune_dir = tmp_path / "data" / "output" / "tune"

    mock_configs_dir.mkdir(parents=True)
    mock_data_input_dir.mkdir(parents=True)
    # TUNE_OUTPUT_DIR создаст сам скрипт

    # 2. Создаем мок-файлы

    # Базовый конфиг
    mock_base_config_path = mock_configs_dir / "config.yaml"
    mock_base_config = {"solver": {"random_seed": 0}, "buffer": 0.25}
    mock_base_config_path.write_text(yaml.dump(mock_base_config))

    # Мок-датасет
    mock_dataset_path = mock_data_input_dir / "smoke_data.csv"
    mock_dataset_path.write_text("id,start,end\n1,2,3")

    # Минимальная сетка (1 датасет, 2 комбинации)
    mock_tune_grid_path = mock_configs_dir / "tune_grid.yaml"
    mock_tune_grid = {
        "datasets": [str(mock_dataset_path)],
        "context": {"solver.num_workers": 8},
        "model": {"grid": {"activation_penalty": [1, 5]}},
        # 1 dataset * 2 combos = 2 total runs
    }
    mock_tune_grid_path.write_text(yaml.dump(mock_tune_grid))

    # 3. Патчим константы в scripts.tune, чтобы он смотрел на tmp_path
    monkeypatch.setattr("scripts.tune.BASE_CONFIG_PATH", mock_base_config_path)
    monkeypatch.setattr("scripts.tune.TUNE_GRID_PATH", mock_tune_grid_path)
    monkeypatch.setattr("scripts.tune.TUNE_OUTPUT_DIR", mock_data_output_tune_dir)

    return mock_data_output_tune_dir, mock_dataset_path


def test_tune_main_smoke_run(mock_fs, mocker):
    """
    Дымовой тест: запускает tune_main() и мокает run_pipeline.
    Проверяет, что:
    1. run_pipeline вызвана 2 раза.
    2. Артефакты (run-0001, run-0002) созданы.
    3. Итоговый tuning_results.csv создан и корректно заполнен.
    """

    mock_output_dir, mock_dataset_path = mock_fs

    # --- Настройка Мока для run_pipeline ---

    # Нам нужен "side_effect", который симулирует то,
    # что делает run_pipeline:
    # 1. Принимает output_dir
    # 2. Создает там metrics.json
    # 3. Возвращает словарь с результатом

    def mock_run_pipeline_side_effect(config_path, input_path, output_dir):
        # Проверяем, что input_path корректный
        assert input_path == mock_dataset_path

        # Симулируем создание артефактов
        metrics_path = output_dir / "metrics.json"

        # Определяем, какой конфиг нам передали (по config_path)
        run_cfg = yaml.safe_load(config_path.read_text())
        penalty = run_cfg["activation_penalty"]

        # Генерируем разные метрики для разных запусков
        if penalty == 1:
            metrics_data = {"utilization": 0.8, "total_cost": 100, "num_anesthetists": 1}
            runtime = 10.5
        else:  # penalty == 5
            metrics_data = {"utilization": 0.9, "total_cost": 200, "num_anesthetists": 2}
            runtime = 20.0

        metrics_path.write_text(json.dumps(metrics_data))

        # Возвращаем то, что вернул бы run_pipeline
        return {
            "valid": True,
            "status": "OPTIMAL",
            "runtime_seconds": runtime,
            "artifacts": {
                "metrics": metrics_path,
                # ... другие артефакты ...
            },
        }

    # Патчим (мокаем) функцию в том модуле, ГДЕ ОНА ИСПОЛЬЗУЕТСЯ (scripts.tune)
    mock_run_pipeline = mocker.patch(
        "scripts.tune.run_pipeline", side_effect=mock_run_pipeline_side_effect
    )

    # --- Запуск ---
    # Перехватываем sys.exit(0)
    exit_code = tune_main()

    # (EN) Check that the function reported success (exit code 0)
    assert exit_code == 0

    # --- Проверки ---

    # 1. Проверяем, что run_pipeline вызвали 2 раза (1 датасет * 2 комбинации)
    assert mock_run_pipeline.call_count == 2

    # 2. Проверяем, что папки артефактов созданы
    run1_dir = mock_output_dir / "run-0001"
    run2_dir = mock_output_dir / "run-0002"
    assert run1_dir.exists()
    assert run2_dir.exists()

    # 3. Проверяем, что конфиги и метрики в них созданы (это делает mock_run_pipeline_side_effect)
    assert (run1_dir / "config_run.yaml").exists()
    assert (run1_dir / "metrics.json").exists()
    assert (run2_dir / "config_run.yaml").exists()
    assert (run2_dir / "metrics.json").exists()

    # 4. Проверяем главный артефакт - tuning_results.csv
    results_csv_path = mock_output_dir / "tuning_results.csv"
    assert results_csv_path.exists()

    with results_csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2  # 2 строки данных

    # Проверяем строки (порядок может быть разный, т.к. dict не гарантирует порядок)
    row1 = rows[0]
    row2 = rows[1]

    # Приводим к типу float для сравнения
    assert float(row1["activation_penalty"]) == 1.0
    assert float(row1["utilization"]) == 0.8
    assert float(row1["runtime_sec"]) == 10.5
    assert row1["status"] == "OPTIMAL"

    assert float(row2["activation_penalty"]) == 5.0
    assert float(row2["utilization"]) == 0.9
    assert float(row2["runtime_sec"]) == 20.0
    assert row2["status"] == "OPTIMAL"
