# INFRA.md — Repository Infrastructure Guidelines

## Purpose

The `infra/` directory hosts local infrastructure assets and automation utilities used during development and research.
It provides a clear separation between **local tooling** and **continuous integration (CI)** logic, which lives under `.github/workflows/`.

The folder is **not part of the Python package** (`src/opmed`) and contains no production code or deployment scripts.
Its purpose is to centralize developer-side automation and experimental tools.

---

## Scope of Contents

Typical items allowed in `infra/`:

- **Local automation scripts** — helper scripts for data preparation, environment setup, backups, or reproducible experiments.
- **Experiment tracking configurations** — local MLflow or similar trackers (`mlruns/`, `mlflow_local/`) used to log solver runs and artifacts.
- **Infrastructure templates** — optional Docker Compose or Terraform definitions for *local* use only (not for deployment).
- **Workflow prototypes** — optional DAG or pipeline skeletons (Airflow, Prefect, etc.) kept as **non-executable templates** for future orchestration integration.

These elements support the reproducibility and automation of experiments without introducing heavy infrastructure dependencies.

---

## Out of Scope

Do **not** place the following items under `infra/`:

- CI/CD definitions or pipelines (should reside under `.github/workflows/`).
- Deployment or production orchestration scripts.
- API secrets, tokens, or credentials.
- Runtime artifacts (model weights, datasets, large logs) used by production services.
- Any code imported by `src/opmed` or executed in CI.

---

## Relationship to Other Folders

- `.github/workflows/` → CI/CD configuration (linting, tests, build).
- `src/` → source code of the Opmed package.
- `infra/` → local automation and research utilities (developer domain).
- `schemas/` → generated JSON Schemas for data contracts.

---

## Notes

`infra/` should not contain `__init__.py` and must never be imported as a Python module.
Files placed here are executed manually or via Makefile targets, not through automated CI pipelines.

Example (optional local structure):

    infra/
        mlflow_local/
        scripts/
            export_results.ps1
            cleanup_artifacts.sh
        templates/
            airflow_dag_example.py
        docker-compose.local.yml

---

**Criterion of completeness:**
This document exists under `docs/ARCHITECTURE/INFRA.md` and clearly defines what belongs and what does not belong in `infra/`.
Developers and reviewers can unambiguously distinguish between local infrastructure and CI/CD assets.
