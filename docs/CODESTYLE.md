# Opmed Code Style Guide

This document defines the coding conventions used in the Opmed Optimization project.  
It complements automated linters (black, ruff, mypy) and explains *why* we follow these rules.

---

## 1. General Principles

- Code must be readable, consistent, and reproducible.  
- All Python files use **UTF-8**, **LF** line endings, and **4 spaces** for indentation.  
- **Maximum line length:** 100 characters.  
- Use **double quotes** for strings ("text") except when a single quote makes escaping cleaner.  
- Avoid wildcard imports (from x import *).  
- Each public module must include a module-level docstring explaining its purpose.

---

## 2. Type Hints

Type annotations are mandatory for all **public APIs**:
- All function arguments and return values must have explicit types.
- Class attributes exposed to other modules must be typed (using dataclasses, pydantic, or normal annotations).
- Internal helper functions (prefixed with "_") may omit type hints if self-documenting.

Mypy runs in **strict** mode; avoid using `Any` unless absolutely necessary.

Example:

    def build_model(surgeries: list[Surgery], cfg: Config) -> CpSatModelBundle:
        ...

---

## 3. Docstrings

All public functions, classes, and modules must have docstrings in either **Google** or **NumPy** style.  
Choose one style per file and remain consistent.

### 3.1 Google Style Example

    def solve(bundle: CpSatModelBundle, time_limit: int) -> Solution:
        """Solves the CP-SAT model within a given time limit.

        Args:
            bundle (CpSatModelBundle): The model, variables, and auxiliary data.
            time_limit (int): Solver time limit in seconds.

        Returns:
            Solution: The best feasible solution found.
        """

### 3.2 NumPy Style Example

    def validate(solution: Solution) -> bool:
        """Check schedule feasibility.

        Parameters
        ----------
        solution : Solution
            The solution to validate.

        Returns
        -------
        bool
            True if the schedule satisfies all constraints.
        """

---

## 4. Imports and Structure

- Use **absolute imports** for project modules: from opmed.solver_core import model_builder  
- Standard library → third-party → local imports, separated by one blank line.  
- `__init__.py` files should be minimal — usually only define the public interface.

---

## 5. Naming Conventions

| Element | Style | Example |
|----------|--------|----------|
| Modules / packages | `snake_case` | `data_loader`, `solver_core` |
| Classes | `PascalCase` | `SurgeryValidator` |
| Functions / methods | `snake_case` | `build_model()` |
| Constants | `UPPER_CASE` | `TIME_UNIT` |
| Private helpers | `_leading_underscore` | `_compute_overlap()` |

---

## 6. Linting and Formatting

All code must pass:

    make lint

which runs:
- **ruff** (ruff check . --fix) for style and import order  
- **black** for formatting  
- **mypy** for type checking  

CI will reject pull requests that fail any of these.

---

## 7. Commit Policy

Each commit must represent a logically complete change:
- Run `pre-commit run --all-files` before committing.  
- Do not commit generated files (data/output, .cache, etc.).  
- Prefer small, clear commits over large mixed ones.

---

## 8. Documentation Consistency

Docstrings and type hints must agree:
- Parameter names and order must match.  
- Return types in the docstring must match the annotated types.  
- If behavior changes, update both code and documentation together.

---

*Following this guide guarantees clean diffs, consistent formatting, and reproducible builds.*
