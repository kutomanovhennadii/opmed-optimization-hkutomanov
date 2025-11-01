# DataLoader & Post-Load Adapter (Design Doc)

Document for the orchestrator. Describes three components of the data loading layer:

* `ConfigLoader` — configuration loading and validation
* `SurgeriesLoader` — loading surgeries from CSV → structured result
* `LoadResultHandler` — post-load reaction (error reporting / data extraction)

Files:

* `src/opmed/dataloader/config_loader.py`
* `src/opmed/dataloader/surgeries_loader.py`
* `src/opmed/dataloader/postload_handler.py`
* `src/opmed/dataloader/types.py` (shared structure `LoadResult`)

---

## 1) ConfigLoader

**File:** `src/opmed/dataloader/config_loader.py`
**Class:** `ConfigLoader`
**Purpose:** read `config.yaml`, validate using `opmed.schemas.models.Config`, return a `Config` object with defaults.

### Responsibility (SRP)
* Read YAML (`.yaml|.yml`, UTF-8) via `yaml.safe_load`
* Structural validation (root must be a mapping)
* Validate with Pydantic model `Config` (`extra="forbid"`)
* Raise clear `ConfigError` (with `source` and `suggested_action`)

### Public API
    from pathlib import Path
    from opmed.schemas.models import Config

    cfg = ConfigLoader().load(Path("config.yaml"))
    # -> Config

### Errors
* File not found / invalid extension / corrupted YAML → `ConfigError`
* Schema mismatch (wrong types, extra keys) → `ConfigError`

### DoD
* Invalid YAML produces human-readable error message
* Valid YAML returns a valid `Config` with defaults

---

## 2) SurgeriesLoader

**File:** `src/opmed/dataloader/surgeries_loader.py`
**Class:** `SurgeriesLoader`
**Purpose:** read surgery data from CSV and return a structured result usable for solving and error reporting.

### Key Idea
The loader **does not raise exceptions** for row-level errors. It collects **all issues** and returns them together with the data, making orchestration predictable.

### Input Contract
* Format: standard **CSV**, UTF-8, delimiter `,`
* Required columns: `surgery_id,start_time,end_time`
* Datetimes are read “as is” (`datetime.fromisoformat`), **without** UTC normalization

### Output Contract
Returns a **structure**, not a list: `LoadResult` (see below).

* If `errors` empty → `success=True`, `surgeries=[...sorted by start_time...]`
* If issues exist → `success=False`, `surgeries=[]`, `errors=[{...}]`

### Row-Level Validation
* Empty `surgery_id` → issue
* Unparsable `start_time` or `end_time` → issue
* `start_time >= end_time` → issue
* Duplicate `surgery_id` → issue; the **first** valid entry is kept, duplicates skipped

### Fatal Errors (immediate `DataError`)
* File missing
* No header in CSV
* Missing required columns in header

### Public API
    from pathlib import Path
    from opmed.dataloader.surgeries_loader import SurgeriesLoader

    result = SurgeriesLoader().load(Path("data/surgeries.csv"))
    # result: LoadResult

---

## 3) LoadResult (common result model)

**File:** `src/opmed/dataloader/types.py`
**Class:** `LoadResult` (`@dataclass(slots=True)`)

### Fields
* `success: bool` — data valid for pipeline
* `surgeries: list[Surgery]` — valid surgeries (only if `success=True`)
* `errors: list[dict]` — list of problematic rows
  * keys: `kind`, `line_no`, `surgery_id` (optional), `message`
* `total_rows: int` — number of rows in CSV
* `kept_rows: int` — number of accepted surgeries

### Example Error
    {
      "kind": "invalid_datetime",
      "line_no": 10,
      "surgery_id": "S015",
      "message": "Invalid datetime format: ..."
    }

---

## 4) Post-Load Handler (reaction to load result)

**File:** `src/opmed/dataloader/postload_handler.py`
**Class:** `LoadResultHandler`
**Purpose:** unified orchestration response to load result:

* If `success=False` → writes detailed error report and returns `None`
* If `success=True` → returns `list[Surgery]` for the next stage

### Public API
    from pathlib import Path
    from opmed.dataloader.postload_handler import LoadResultHandler
    from opmed.dataloader.surgeries_loader import SurgeriesLoader

    loader = SurgeriesLoader()
    handler = LoadResultHandler(output_dir=Path("data/output"))

    result = loader.load(Path("data/surgeries.csv"))
    surgeries = handler.handle(result)
    # surgeries is list[Surgery] or None (if errors occurred; see load_errors.json)

### Artifacts
* `data/output/load_errors.json` — created **only** when errors exist:
    [
      {"kind": "duplicate_id", "line_no": 7, "surgery_id": "S003", "message": "Duplicate surgery_id (later occurrence skipped)"},
      {"kind": "non_positive_duration", "line_no": 9, "surgery_id": "S005", "message": "start_time >= end_time"}
    ]

---

## 5) End-to-End Example (for orchestrator)

    from pathlib import Path
    from opmed.dataloader.config_loader import ConfigLoader
    from opmed.dataloader.surgeries_loader import SurgeriesLoader
    from opmed.dataloader.postload_handler import LoadResultHandler

    cfg = ConfigLoader().load(Path("config.yaml"))
    loader = SurgeriesLoader()
    result = loader.load(Path("data/surgeries.csv"))
    surgeries = LoadResultHandler(output_dir=Path("data/output")).handle(result)

    if surgeries is None:
        # orchestrator stops here; see data/output/load_errors.json for details
        raise SystemExit(1)

    # otherwise pass surgeries to SolverCore

---

## 6) Test Scenarios (minimum)

1. **ConfigLoader**
   * OK: valid YAML → `Config`
   * BAD: missing file / empty / corrupted YAML / extra keys → `ConfigError`

2. **SurgeriesLoader**
   * OK: valid CSV → `LoadResult(success=True, surgeries>0, errors=[])`
   * BAD (row-level): duplicates, `start>=end`, bad datetime → `LoadResult(success=False, surgeries=[], errors=[...])`
   * BAD (fatal): missing file / no header / missing required columns → `DataError`

3. **LoadResultHandler**
   * With `success=True` returns `list[Surgery]`, **without** creating `load_errors.json`
   * With `success=False` writes `load_errors.json`, returns `None`

---

## 7) Responsibility Boundaries

* **DataLoader** never changes business values (e.g. timestamps). It only validates and reports.
* **Tick conversion** belongs to SolverCore; DataLoader keeps `datetime` as is.
* **Batch error reporting** — all issues collected in one run.
* **Error output format** — flat JSON list, suitable for CI logs and UX.

---

## 8) Integration Readiness

* Interface **stable**: orchestrator depends only on `LoadResult.success`, `errors`, and `surgeries`.
* Documentation reports: `load_errors.json` auto-generated when `success=False`.
* Zero side effects on success: no files, no hidden state.

---

## 9) TL;DR (quick use)

* Load config: `cfg = ConfigLoader().load(Path("config.yaml"))`
* Load surgeries: `result = SurgeriesLoader().load(Path("data/surgeries.csv"))`
* React:
    * `surgeries = LoadResultHandler(Path("data/output")).handle(result)`
    * if `surgeries is None` → check `data/output/load_errors.json` and fix CSV
    * else — pass `surgeries` to `ModelBuilder` / `SolverCore`.

Ready for orchestrator integration.
