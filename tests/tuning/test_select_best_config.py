# tests/tuning/test_select_best_config.py
"""
Tests for the select_best_config.py script (Epic 7, Task 7.3.3).

We test the helper functions as unit tests and the main()
function as a smoke test, mocking the file system and
the final write operations.
"""

import csv

import pandas as pd
import pytest
import yaml

# Functions to test
from scripts.select_best_config import (
    main as select_main,
)
from scripts.select_best_config import (
    set_nested_key,
)

# --- Unit Tests for Helpers ---


def test_set_nested_key():
    """Tests the nested key setting utility."""
    d = {}
    set_nested_key(d, "solver.num_workers", 8)
    assert d == {"solver": {"num_workers": 8}}

    set_nested_key(d, "solver.random_seed", 42)
    assert d == {"solver": {"num_workers": 8, "random_seed": 42}}

    set_nested_key(d, "activation_penalty", 10)
    assert d == {
        "solver": {"num_workers": 8, "random_seed": 42},
        "activation_penalty": 10,
    }


# --- Smoke Test for main() ---


@pytest.fixture
def mock_selector_fs(tmp_path, monkeypatch):
    """
    Creates a mock file system for the selector script.
    - Mocks all input paths (grid, base config, results CSV).
    - Mocks all output paths (best config, docs report).
    """
    configs_dir = tmp_path / "configs"
    tune_output_dir = tmp_path / "data" / "output" / "tune"
    docs_dir = tmp_path / "docs"

    configs_dir.mkdir(parents=True)
    tune_output_dir.mkdir(parents=True)
    docs_dir.mkdir(parents=True)

    # 1. Mock tune_grid.yaml (defines objectives)
    mock_tune_grid_path = configs_dir / "tune_grid.yaml"
    mock_tune_grid = {
        "objective_primary": "utilization",
        "objective_primary_goal": "maximize",
        "objective_secondary": "runtime_sec",
        "objective_secondary_goal": "minimize",
    }
    mock_tune_grid_path.write_text(yaml.dump(mock_tune_grid))

    # 2. Mock base config.yaml (what we load to overwrite)
    mock_base_config_path = configs_dir / "config.yaml"
    mock_base_config = {"solver": {"num_workers": 1, "random_seed": 0}}
    mock_base_config_path.write_text(yaml.dump(mock_base_config))

    # 3. Mock tuning_results.csv (the most important part)
    mock_results_csv_path = tune_output_dir / "tuning_results.csv"

    # We will test sorting and filtering.
    # The winner should be 'run-001' (best util, lowest runtime for that util).
    mock_csv_data = [
        # Parameters
        [
            "run_id",
            "dataset",
            "status",
            "activation_penalty",
            "solver.search_branching",
            "utilization",
            "runtime_sec",
            "total_cost",
        ],
        # The Best Run (Winner)
        ["run-001", "small", "OPTIMAL", 5, "PORTFOLIO", 0.90, 10.0, 150.0],
        # Worse util
        ["run-002", "small", "OPTIMAL", 1, "AUTOMATIC", 0.80, 5.0, 200.0],
        # Same util, but slower runtime
        ["run-003", "small", "OPTIMAL", 10, "FIXED_SEARCH", 0.90, 15.0, 140.0],
        # A failed run (should be filtered out)
        ["run-004", "small", "CRASH", 1, "AUTOMATIC", 0.0, 1.0, 0.0],
        # A FEASIBLE run (should be kept)
        ["run-005", "small", "FEASIBLE", 15, "PORTFOLIO", 0.85, 8.0, 180.0],
    ]

    with mock_results_csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(mock_csv_data)

    # 4. Mock output paths
    mock_best_config_path = configs_dir / "best_config.yaml"
    mock_docs_path = docs_dir / "RESULTS_tuning.md"

    # 5. Monkeypatch the constants in select_best_config.py
    monkeypatch.setattr("scripts.select_best_config.BASE_CONFIG_PATH", mock_base_config_path)
    monkeypatch.setattr("scripts.select_best_config.TUNE_GRID_PATH", mock_tune_grid_path)
    monkeypatch.setattr("scripts.select_best_config.RESULTS_CSV_PATH", mock_results_csv_path)
    monkeypatch.setattr("scripts.select_best_config.BEST_CONFIG_PATH", mock_best_config_path)
    monkeypatch.setattr("scripts.select_best_config.RESULTS_DOC_PATH", mock_docs_path)

    return {
        "base_cfg_path": mock_base_config_path,
        "results_csv_path": mock_results_csv_path,
        "best_cfg_path": mock_best_config_path,
        "docs_path": mock_docs_path,
        "base_cfg_content": mock_base_config,
    }


def test_select_main_smoke_run(mock_selector_fs, mocker):
    """
    Tests the main() function logic:
    - Mocks the I/O functions we don't want to test (save_best_config, update_markdown_report).
    - Runs main() (which *does* read the mock CSV).
    - Checks that the mocked functions were called with the *correct* data.
    """

    # 1. Mock the two functions that write to disk
    mock_save = mocker.patch("scripts.select_best_config.save_best_config")
    mock_report = mocker.patch("scripts.select_best_config.update_markdown_report")

    # 2. Run the main function
    exit_code = select_main()

    # 3. Check for success
    assert exit_code == 0

    # --- 4. Verify save_best_config ---

    # Check it was called exactly once
    mock_save.assert_called_once()

    # Get the arguments it was called with
    call_args = mock_save.call_args[0]

    # Arg 0: base_cfg
    base_cfg_arg = call_args[0]
    assert base_cfg_arg == mock_selector_fs["base_cfg_content"]

    # Arg 1: best_params (the most important check)
    best_params_arg = call_args[1]

    # Check that we picked the parameters from run-001
    assert best_params_arg["activation_penalty"] == 5
    assert best_params_arg["solver.search_branching"] == "PORTFOLIO"

    # --- 5. Verify update_markdown_report ---

    # Check it was called exactly once
    mock_report.assert_called_once()

    # Get the arguments
    call_args = mock_report.call_args[0]

    # Arg 0: df_top5
    df_top5_arg = call_args[0]
    assert isinstance(df_top5_arg, pd.DataFrame)
    # 4 rows: run-001, run-003, run-005, run-002 (run-004 was filtered)
    assert len(df_top5_arg) == 4

    # Arg 1: best_run
    best_run_arg = call_args[1]
    assert isinstance(best_run_arg, pd.Series)
    assert best_run_arg["run_id"] == "run-001"  # Check it's the winner
    assert best_run_arg["utilization"] == 0.90
    assert best_run_arg["runtime_sec"] == 10.0
