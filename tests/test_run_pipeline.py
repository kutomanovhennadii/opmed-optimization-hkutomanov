import json
from pathlib import Path

import pytest

from scripts.run import run_pipeline


@pytest.mark.skip(reason="Heavy integration test — use only for manual inspection.")
@pytest.mark.live
def test_run_pipeline_live_creates_real_artifacts():
    """
    Живой интеграционный тест: запускает реальный пайплайн
    и пишет артефакты прямо в data/output/, чтобы их можно было посмотреть глазами.
    """

    cfg_path = Path("config/config.yaml")
    input_path = Path("data/input/synthetic_2d_2r.csv")
    output_dir = Path("data/output")

    assert cfg_path.exists(), f"Config file not found: {cfg_path}"
    assert input_path.exists(), f"Input CSV not found: {input_path}"

    result = run_pipeline(cfg_path, input_path, output_dir)

    arts = result["artifacts"]

    print("\n[Artifacts created]")
    for name, path in arts.items():
        if path:
            print(f"{name:>20}: {Path(path).resolve()}")

    # --- базовые проверки ---
    val_report = arts["validation_report"]
    metrics = arts["metrics"]
    solution = arts["solution_csv"]

    assert val_report and Path(val_report).exists()
    assert metrics and Path(metrics).exists()
    assert solution and Path(solution).exists()

    with open(val_report, encoding="utf-8") as f:
        report = json.load(f)
    print(f"\nValidation valid={report['valid']}")

    with open(metrics, encoding="utf-8") as f:
        summary = json.load(f)
    print(f"Utilization={summary.get('utilization')} total_cost={summary.get('total_cost')}")

    if report["valid"]:
        plot = arts.get("solution_plot")
        assert plot and Path(plot).exists()
        print(f"Plot: {plot}")
    else:
        print("Plot skipped (invalid schedule)")

    print("\n[Pipeline completed successfully]")


# ----------------------------------------------------------------------------------
# Lightweight pipeline smoke-test (default)
# ----------------------------------------------------------------------------------
class _FakeOptimizer:
    def __init__(self, cfg): ...
    def solve(self, bundle):
        # возвращаем минимальный SolveResult без реального решения
        return {
            "status": "DUMMY",
            "objective": 0.0,
            "runtime": 0.01,
            "assignments": [],
            "solver": None,
        }


def test_run_pipeline_stub(monkeypatch, tmp_path):
    """
    Мгновенный тест пайплайна без вызова CP-SAT.
    Проверяет, что структура пайплайна, загрузка конфигурации
    и сборка артефактов выполняются без ошибок.
    """

    from scripts import run

    monkeypatch.setattr(run, "Optimizer", _FakeOptimizer)

    cfg_path = Path("config/config.yaml")
    input_path = Path("data/input/synthetic_2d_2r.csv")
    output_dir = tmp_path / "out"

    result = run_pipeline(cfg_path, input_path, output_dir)

    assert isinstance(result, dict)
    assert "artifacts" in result
    assert "valid" in result
    assert result["status"] == "DUMMY"
    print("Pipeline stub test passed — no solver invoked.")
