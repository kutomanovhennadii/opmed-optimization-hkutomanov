# scripts/tune.py
"""
Скрипт для гиперпараметрической оптимизации (тюнинга) конвейера Opmed.

Задачи (Эпик 7, Задача 7.3.2):
1. Читает базовый config.yaml.
2. Читает configs/tune_grid.yaml (сетку параметров, датасеты, цели).
3. Генерирует все комбинации параметров (декартово произведение).
4. Для каждой комбинации и каждого датасета:
    a. Создает уникальную директорию (напр., data/output/tune/run-0001/).
    b. Создает временный config.yaml для этого запуска в этой директории.
    c. Вызывает `run_pipeline`, передавая пути к конфигу, данным и выходу.
    d. Собирает ключевые метрики (status, utilization, runtime и т.д.).
5. Записывает все результаты в единый data/output/tune/tuning_results.csv.
"""

from __future__ import annotations

import csv
import itertools
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml  # Используем pyyaml для работы с YAML

from opmed.errors import OpmedError
from opmed.schemas.models import Config  # noqa: F401
from scripts.run import run_pipeline

# --- Константы ---
BASE_CONFIG_PATH = Path("config/config.yaml")
TUNE_GRID_PATH = Path("config/tune_grid.yaml")
TUNE_OUTPUT_DIR = Path("data/output/tune")


def setup_logging() -> None:
    """Настраивает базовое логирование в stdout."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_yaml_config(path: Path) -> dict[str, Any]:
    """Загружает YAML файл как словарь."""
    logging.info(f"Загрузка конфигурации: {path}")
    if not path.exists():
        logging.error(f"Файл конфигурации не найден: {path}")
        raise FileNotFoundError(f"Файл не найден: {path}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        logging.error(f"Ошибка парсинга YAML в {path}: {e}")
        raise


def set_nested_key(config_dict: dict, key: str, value: Any) -> None:
    """
    Устанавливает вложенный ключ в словаре по строке 'a.b.c'.
    Пример: set_nested_key(cfg, 'solver.num_workers', 8)
    -> cfg['solver']['num_workers'] = 8
    """
    keys = key.split(".")
    d = config_dict
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = value


def generate_combinations(tune_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Генерирует декартово произведение параметров из tune_grid.yaml.
    Поддерживает разделение 'model' и 'solver'.
    """
    grid_params = {}

    # 1. Собираем параметры 'model' (верхнего уровня)
    model_grid = tune_cfg.get("model", {}).get("grid", {})
    grid_params.update(model_grid)

    # 2. Собираем параметры 'solver' (вложенные)
    solver_grid = tune_cfg.get("solver", {}).get("grid", {})
    for key, values in solver_grid.items():
        # Преобразуем в "плоский" ключ
        grid_params[f"solver.{key}"] = values

    if not grid_params:
        logging.warning("Сетка (grid) в tune_grid.yaml пуста. Будет 1 комбинация.")
        return [{}]

    # 3. Генерируем декартово произведение
    keys, value_lists = zip(*grid_params.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*value_lists)]

    logging.info(f"Сгенерировано {len(combinations)} комбинаций параметров.")
    return combinations


def apply_run_config(
    base_cfg: dict[str, Any],
    context: dict[str, Any],
    combo: dict[str, Any],
    run_output_dir: Path,
) -> Path:
    """
    Создает и сохраняет config.yaml для конкретного запуска.

    1. Берет base_cfg.
    2. Перезаписывает значениями из context.
    3. Перезаписывает значениями из combo (комбинация).
    4. Принудительно устанавливает 'output_dir'.
    5. Сохраняет как YAML в run_output_dir.

    Возвращает: Path к созданному config.yaml
    """
    # 1. Глубокая копия базы (json - самый простой способ)
    run_cfg = json.loads(json.dumps(base_cfg))

    # 2. Применяем фиксированный 'context'
    for key, value in context.items():
        set_nested_key(run_cfg, key, value)

    # 3. Применяем параметры этой 'combination'
    for key, value in combo.items():
        set_nested_key(run_cfg, key, value)

    # 4. Принудительно устанавливаем output_dir (важнейший шаг)
    run_cfg["output_dir"] = str(run_output_dir)
    # Также убедимся, что пайплайн сохранит артефакты
    set_nested_key(run_cfg, "validation.write_report", True)
    set_nested_key(run_cfg, "metrics.save_metrics", True)
    set_nested_key(run_cfg, "visualization.save_plot", True)

    # 5. Сохраняем как "доказательство"
    temp_config_path = run_output_dir / "config_run.yaml"
    try:
        with temp_config_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(run_cfg, f, default_flow_style=False)
    except Exception as e:
        logging.error(f"Не удалось записать временный конфиг {temp_config_path}: {e}")
        raise

    return temp_config_path


def get_metrics_from_file(
    metrics_path: Path | str | None,
) -> dict[str, Any]:
    """Безопасно читает метрики из metrics.json."""
    if not metrics_path or not Path(metrics_path).exists():
        return {}

    try:
        data = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
        # Возвращаем только то, что нам нужно для CSV
        return {
            "utilization": data.get("utilization"),
            "total_cost": data.get("total_cost"),
            "num_anesthetists": data.get("num_anesthetists"),
            "num_rooms_used": data.get("num_rooms_used"),
        }
    except Exception as e:
        logging.warning(f"Не удалось прочитать {metrics_path}: {e}")
        return {}


def main() -> int:
    """Главная функция выполнения тюнинга."""
    setup_logging()
    t_start = time.perf_counter()

    RESULTS_CSV_PATH = TUNE_OUTPUT_DIR / "tuning_results.csv"

    try:
        # --- 1. Подготовка ---
        base_cfg = load_yaml_config(BASE_CONFIG_PATH)
        tune_cfg = load_yaml_config(TUNE_GRID_PATH)

        datasets = tune_cfg.get("datasets", [])
        if not datasets:
            logging.error("В tune_grid.yaml не найден ключ 'datasets'. Остановка.")
            return 1

        context = tune_cfg.get("context", {})
        combinations = generate_combinations(tune_cfg)

        TUNE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # --- 2. Подготовка CSV ---
        # Собираем все ключи параметров для заголовка
        header = ["run_id", "dataset"]
        header.extend(combinations[0].keys())
        # ... и ключи метрик (цели + наблюдаемые)
        header.extend(
            [
                "status",
                "utilization",
                "runtime_sec",
                "total_cost",
                "num_anesthetists",
                "num_rooms_used",
                "is_valid",
            ]
        )

        total_runs = len(datasets) * len(combinations)
        logging.info(
            f"Всего запусков: {total_runs} ({len(datasets)} датасетов x {len(combinations)} комбинаций)"
        )

        with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=header, extrasaction="ignore")
            writer.writeheader()

            run_id_counter = 0

            # --- 3. Главный цикл тюнинга ---
            for dataset_path_str in datasets:
                dataset_path = Path(dataset_path_str)
                if not dataset_path.exists():
                    logging.warning(f"Пропуск: датасет не найден {dataset_path}")
                    continue

                for combo in combinations:
                    run_id_counter += 1
                    run_id_str = f"run-{run_id_counter:04d}"

                    log_prefix = (
                        f"[{run_id_counter}/{total_runs}] {run_id_str} ({dataset_path.name})"
                    )
                    logging.info(f"--- {log_prefix} ---")

                    # --- 4. Изоляция артефактов ---
                    run_output_dir = TUNE_OUTPUT_DIR / run_id_str
                    if run_output_dir.exists():
                        shutil.rmtree(run_output_dir)
                    run_output_dir.mkdir()

                    # Готовим строку для CSV (параметры)
                    csv_row = {"run_id": run_id_str, "dataset": dataset_path.name}
                    csv_row.update(combo)

                    metrics: dict[str, Any] = {}

                    try:
                        # 4a. Создаем и сохраняем конфиг для этого запуска
                        temp_config_path = apply_run_config(
                            base_cfg, context, combo, run_output_dir
                        )

                        # --- 5. Запуск пайплайна ---
                        result = run_pipeline(
                            config_path=temp_config_path,
                            input_path=dataset_path,
                            output_dir=run_output_dir,
                        )

                        # --- 6. Сбор метрик ---

                        # 6.1. Базовые метрики из return value
                        status = result.get("status", "UNKNOWN")
                        runtime = result.get("runtime_seconds")
                        is_valid = result.get("valid", False)

                        metrics["status"] = status
                        metrics["runtime_sec"] = runtime
                        metrics["is_valid"] = is_valid

                        if not is_valid:
                            logging.warning(f"{log_prefix} Решение НЕВАЛИДНО (status={status}).")

                        # 6.2. Читаем metrics.json (даже если невалидно,
                        #      там могут быть runtime и status)
                        metrics_path = result["artifacts"].get("metrics")
                        file_metrics = get_metrics_from_file(metrics_path)
                        metrics.update(file_metrics)

                    except OpmedError as e:
                        # Контролируемая ошибка пайплайна (DataError, ConfigError и т.д.)
                        logging.error(f"{log_prefix} FAILED (OpmedError): {e}")
                        metrics = {"status": "PIPELINE_ERROR", "is_valid": False}
                    except Exception as e:
                        # Неконтролируемый сбой (ошибка в коде)
                        logging.error(f"{log_prefix} CRASHED (Exception): {e}", exc_info=True)
                        metrics = {"status": "CRASH", "is_valid": False}

                    # 7. Запись строки в CSV
                    csv_row.update(metrics)
                    writer.writerow(csv_row)
                    csv_file.flush()  # Сбрасываем буфер, чтобы видеть прогресс

    except Exception as e:
        logging.error(f"Критическая ошибка тюнера: {e}", exc_info=True)
        return 1
    finally:
        t_end = time.perf_counter()
        logging.info(f"--- Тюнинг завершен за {(t_end - t_start):.2f} сек. ---")
        logging.info(f"Результаты сохранены в: {RESULTS_CSV_PATH}")
        logging.info(f"Артефакты запусков (конфиги, логи, графики) в: {TUNE_OUTPUT_DIR}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
