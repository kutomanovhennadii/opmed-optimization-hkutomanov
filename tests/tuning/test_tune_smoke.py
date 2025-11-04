"""
Tests for the script scripts/tune.py (Epic 7, Task 7.3.2).

We test the orchestration logic (config generation, invocation, metrics collection),
but mock the heavy `run_pipeline` call so tests run instantly.
"""

import csv
import json
import os
from pathlib import Path

import pytest
import yaml

from scripts.tune import (
    apply_run_config,
    generate_combinations,
    get_metrics_from_file,
    set_nested_key,
)

# --- Unit tests for helper functions ---


def test_set_nested_key():
    """Tests the utility for setting nested keys in a dictionary."""
    d = {}
    set_nested_key(d, "solver.num_workers", 8)
    assert d == {"solver": {"num_workers": 8}}

    set_nested_key(d, "solver.random_seed", 42)
    assert d == {"solver": {"num_workers": 8, "random_seed": 42}}

    set_nested_key(d, "activation_penalty", 10)
    assert d == {"solver": {"num_workers": 8, "random_seed": 42}, "activation_penalty": 10}


def test_generate_combinations():
    """Tests the Cartesian product generator."""
    tune_cfg = {
        "model": {"grid": {"activation_penalty": [1, 5]}},
        "solver": {
            "grid": {"search_branching": ["AUTOMATIC", "PORTFOLIO"], "linearization_level": [0]}
        },
    }

    combos = generate_combinations(tune_cfg)

    # Expect 2 * 2 * 1 = 4 combinations
    assert len(combos) == 4

    # Verify that keys are properly flattened
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

    # Compare as sets since order is not guaranteed
    expected_set = {tuple(sorted(d.items())) for d in expected_combos}
    actual_set = {tuple(sorted(d.items())) for d in combos}

    assert actual_set == expected_set


def test_apply_run_config(tmp_path):
    """Tests creation and saving of a temporary configuration file."""
    base_cfg = {"solver": {"random_seed": 0}, "buffer": 0.25}
    context = {"solver.max_time_in_seconds": 60, "buffer": 0.5}  # Context overrides buffer
    combo = {"solver.random_seed": 42, "activation_penalty": 10}
    run_output_dir = tmp_path

    config_path = apply_run_config(base_cfg, context, combo, run_output_dir)

    assert config_path == run_output_dir / "config_run.yaml"
    assert config_path.exists()

    # Load and validate
    saved_cfg = yaml.safe_load(config_path.read_text())

    # 1. 'combo' (seed: 42) overrides 'base' (seed: 0)
    assert saved_cfg["solver"]["random_seed"] == 42
    # 2. 'context' (buffer: 0.5) overrides 'base' (buffer: 0.25)
    assert saved_cfg["buffer"] == 0.5
    # 3. 'context' (time_limit) is added
    assert saved_cfg["solver"]["max_time_in_seconds"] == 60
    # 4. 'combo' (penalty) is added
    assert saved_cfg["activation_penalty"] == 10
    # 5. output_dir is forcibly set
    assert saved_cfg["output_dir"] == str(run_output_dir)
    # 6. Keys for artifact saving are enabled
    assert saved_cfg["metrics"]["save_metrics"] is True
    assert saved_cfg["validation"]["write_report"] is True


def test_get_metrics_from_file(tmp_path):
    """Tests safe reading of metrics.json."""
    metrics_path = tmp_path / "metrics.json"

    # Case 1: File not found
    assert get_metrics_from_file(None) == {}
    assert get_metrics_from_file(metrics_path) == {}

    # Case 2: File exists and is valid
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
        "num_rooms_used": None,  # .get() returns None if the key is missing
    }
    assert get_metrics_from_file(metrics_path) == expected

    # Case 3: File is corrupted (not JSON)
    metrics_path.write_text("not valid json")
    assert get_metrics_from_file(metrics_path) == {}


# --- Smoke test for main() ---


@pytest.fixture
def mock_fs(tmp_path, monkeypatch):
    """
    Creates a complete mock file system for the tuner in tmp_path
    and patches path constants inside tune.py.
    """
    # (1) Create directories
    mock_configs_dir = tmp_path / "configs"
    mock_data_input_dir = tmp_path / "data" / "input"
    mock_data_output_tune_dir = tmp_path / "data" / "output" / "tune"

    mock_configs_dir.mkdir(parents=True)
    mock_data_input_dir.mkdir(parents=True)
    # The script will create TUNE_OUTPUT_DIR on its own

    # (2) Create mock files

    # Base config
    mock_base_config_path = mock_configs_dir / "config.yaml"
    mock_base_config = {"solver": {"random_seed": 0}, "buffer": 0.25}
    mock_base_config_path.write_text(yaml.dump(mock_base_config))

    # Mock dataset
    mock_dataset_path = mock_data_input_dir / "smoke_data.csv"
    mock_dataset_path.write_text("id,start,end\n1,2,3")

    # Minimal tuning grid (1 dataset, 2 combinations)
    mock_tune_grid_path = mock_configs_dir / "tune_grid.yaml"
    mock_tune_grid = {
        "datasets": [str(mock_dataset_path)],
        "context": {"solver.num_workers": 8},
        "model": {"grid": {"activation_penalty": [1, 5]}},
        # 1 dataset × 2 combos = 2 total runs
    }
    mock_tune_grid_path.write_text(yaml.dump(mock_tune_grid))

    # (3) Patch constants in scripts.tune to point to tmp_path.
    # Attributes may not exist (depending on dynamic imports), so we use raising=False.
    monkeypatch.setattr("scripts.tune.IS_STRESS_TUNE", False, raising=False)
    monkeypatch.setattr("scripts.tune.BASE_CONFIG_PATH", mock_base_config_path, raising=False)
    monkeypatch.setattr("scripts.tune.TUNE_GRID_PATH", mock_tune_grid_path, raising=False)
    monkeypatch.setattr("scripts.tune.TUNE_OUTPUT_DIR", mock_data_output_tune_dir, raising=False)

    return mock_data_output_tune_dir, mock_dataset_path


def test_tune_main_smoke_run(mock_fs, mocker):
    """
    Smoke test: runs tune.main() while mocking run_pipeline.
    Verifies that:
      1) run_pipeline is called twice (1 dataset × 2 combos),
      2) artifacts run-0001, run-0002 are created,
      3) tuning_results.csv is correct.
    """
    mock_output_dir, mock_dataset_path = mock_fs
    # mock_output_dir: <tmp>/data/output/tune
    # mock_dataset_path: <tmp>/data/input/smoke_data.csv

    # Root working directory — parent of 'data' folder
    tmp_root = mock_output_dir.parent.parent.parent  # .../<tmp>
    assert (tmp_root / "data").exists()
    os.chdir(tmp_root)  # so that relative paths 'data/...' in tune.py resolve properly

    # --- Prepare configs that tune.main() will read ---
    configs_dir = tmp_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    # Minimal base config (anything valid for your pipeline)
    (configs_dir / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": {"name": "smoke"},
                # Important: output_dir will be overwritten by tune on each run
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    # tune_grid.yaml: 1 dataset and 2 combos (through model.grid — key without prefix)
    (configs_dir / "tune_grid.yaml").write_text(
        yaml.safe_dump(
            {
                "datasets": [str(mock_dataset_path)],  # absolute path to temp CSV
                "context": {},  # can be empty
                "model": {
                    "grid": {
                        # Key without prefix (in model.grid) → appears as "activation_penalty" in run_cfg root
                        "activation_penalty": [1, 5],
                    }
                },
                "solver": {"grid": {}},  # empty to avoid extra combinations
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    # --- Import tune module and patch its environment ---
    import scripts.tune as tune

    # (1) Disable stress mode to use DEFAULT_* paths
    tune.IS_STRESS_TUNE = False

    # (2) Inject our mock configuration files
    tune.DEFAULT_BASE_CONFIG_PATH = configs_dir / "config.yaml"
    tune.DEFAULT_TUNE_GRID_PATH = configs_dir / "tune_grid.yaml"

    # (3) Default output directory in non-stress mode is data/output/<DEFAULT_OUTPUT_DIR_NAME>.
    # Our mock_output_dir == <tmp>/data/output/tune, and the default name is already "tune",
    # so DEFAULT_OUTPUT_DIR_NAME does not need to be changed.

    # --- Mock run_pipeline where it is called (in scripts.tune) ---
    def mock_run_pipeline_side_effect(config_path, input_path, output_dir):
        # Compare resolved paths to avoid confusion between relative and absolute
        assert Path(input_path).resolve() == mock_dataset_path.resolve()

        # Simulate artifacts
        metrics_path = Path(output_dir) / "metrics.json"

        # Read the generated run config
        run_cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
        penalty = run_cfg["activation_penalty"]  # key placed in model.grid without prefix

        if penalty == 1:
            metrics_data = {"utilization": 0.8, "total_cost": 100, "num_anesthetists": 1}
            runtime = 10.5
        else:  # penalty == 5
            metrics_data = {"utilization": 0.9, "total_cost": 200, "num_anesthetists": 2}
            runtime = 20.0

        metrics_path.write_text(json.dumps(metrics_data), encoding="utf-8")

        return {
            "valid": True,
            "status": "OPTIMAL",
            "runtime_seconds": runtime,
            "artifacts": {"metrics": metrics_path},
        }

    mock_run_pipeline = mocker.patch(
        "scripts.tune.run_pipeline", side_effect=mock_run_pipeline_side_effect
    )

    # --- Run the tuner ---
    exit_code = tune.main()
    assert exit_code == 0

    # --- Verify calls and artifacts ---
    assert mock_run_pipeline.call_count == 2  # 1 dataset × 2 values of activation_penalty

    run1_dir = mock_output_dir / "run-0001"
    run2_dir = mock_output_dir / "run-0002"
    assert run1_dir.exists()
    assert run2_dir.exists()
    assert (run1_dir / "config_run.yaml").exists()
    assert (run1_dir / "metrics.json").exists()
    assert (run2_dir / "config_run.yaml").exists()
    assert (run2_dir / "metrics.json").exists()

    results_csv_path = mock_output_dir / "tuning_results.csv"
    assert results_csv_path.exists()

    with results_csv_path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    assert len(rows) == 2

    row1, row2 = rows
    assert float(row1["activation_penalty"]) == 1.0
    assert float(row1["utilization"]) == 0.8
    assert float(row1["runtime_sec"]) == 10.5
    assert row1["status"] == "OPTIMAL"

    assert float(row2["activation_penalty"]) == 5.0
    assert float(row2["utilization"]) == 0.9
    assert float(row2["runtime_sec"]) == 20.0
    assert row2["status"] == "OPTIMAL"
