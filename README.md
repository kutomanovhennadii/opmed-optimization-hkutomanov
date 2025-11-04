# Opmed Optimization Project — Quick Start

Full setup and activation instructions are in **docs/INSTALL.md**.
After completing installation, activate the Poetry environment and run sanity checks:

    make setup
    make check

---

## Overview
Opmed Optimization is a modular CP-SAT–based scheduling engine that allocates anesthesiologists and operating rooms under real-world constraints such as shifts, buffers, and utilization.
Built with Python 3.11, Poetry, and Google OR-Tools, it represents a complete research-to-prototype workflow with reproducible results and MLOps-style hyperparameter tuning.

---

## Repository Layout
    src/opmed/          → Core modules (dataloader, solver_core, validator, visualizer, metrics)
    tests/              → Unit & integration tests
    data/input/         → Synthetic datasets (1d_1r, 2d_2r, 3d_8r)
    data/output/        → Generated artifacts (solution.csv, metrics.json, plots, logs)
    config/             → Main YAML configs
    scripts/            → Entry scripts: run, tune, gen_synthetic_data, select_best_config
    docs/               → Architecture, ADRs, Scrum, installation, tuning results
    infra/              → Local automation and CI helpers
    .github/workflows/  → CI pipelines (lint.yml, tests.yml)

---

## Typical Commands
Run the full optimization pipeline:
    make run

Run unit tests and linters:
    make test
    make lint

Generate synthetic datasets:
    make gendata

Run hyperparameter tuning and select the best configuration:
    make tune
    make tune-best

Regenerate JSON schemas:
    make schemas

Clean caches and artifacts:
    make clean

---

## Outputs
All artifacts are written to **data/output/**:

* **solution.csv** — optimized schedule
* **metrics.json** — key performance metrics
* **solver.log** — solver configuration and status
* **solution_plot.png** — visualized timetable

---

## Documentation
See `/docs/` for:

* **INSTALL.md** – environment setup
* **ARCHITECTURE/** – module and interface design
* **ADRs/** – key architectural decisions
* **scrum/** – epics and implementation plan
* **RESULTS_tuning.md** – tuning outcomes

---

## CI & Quality
GitHub Actions automatically runs:
* **lint.yml** → ruff, black, mypy, pre-commit
* **tests.yml** → pytest with coverage

Local verification shortcut:
    make check

---

## Status
Prototype implementation — complete, reproducible, and modular.
All stages from data loading to tuning are functional and ready for demonstration or future extension.
