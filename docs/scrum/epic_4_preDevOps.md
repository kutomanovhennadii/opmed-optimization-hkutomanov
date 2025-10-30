\# Epic 4 — Pre-DevOps: Repository Skeleton and Standards (src-layout)



Goal: reproducible builds and automatic checks “out of the box”.

Epic artifacts: pyproject.toml, Makefile, .pre-commit-config.yaml, .github/workflows/{lint.yml, tests.yml}, minimal code stubs in src/opmed, base schemas in schemas/.

Definition of Done (DoD): make lint \&\& make test are green locally and in CI; dependency versions are pinned.



\## 4.1 (Must) Folder Structure (synchronization with current)



\### 4.1.1 — Complete src-layout skeleton

Place code here:

src/opmed/{dataloader, solver\_core, validator, visualizer, metrics, \_\_init\_\_.py}

Inside each — \_\_init\_\_.py + an empty module (loader.py, model\_builder.py, optimizer.py, validator.py, plot.py, metrics.py, logger.py) with docstrings.



Add root folders if missing:

tests/, scripts/, data/{input, output}, .github/workflows/



Criterion: python -c "import opmed; import opmed.solver\_core" does not fail.



\### 4.1.2 — Minimal stubs and entry points

scripts/run.py (argparse, for now print("run placeholder"))

scripts/tune.py (argparse, for now print("tune placeholder"))



Criterion: python scripts/run.py --help and tune.py --help work.



\### 4.1.3 — Basic repository files

Add/update: README.md, LICENSE, CHANGELOG.md, .gitignore



.gitignore:

\_\_pycache\_\_/, .pytest\_cache/, .mypy\_cache/, .ruff\_cache/, data/output/, \*.pyc



Criterion: after local run, git status is clean.



\## 4.2 (Must) Project initialization (pyproject, versions, src-layout)



\### 4.2.1 — Create/update pyproject.toml for src-layout

Required sections:



\[build-system] → setuptools>=68, wheel

\[project] → name="opmed", version="0.1.0", requires-python=">=3.11", readme="README.md"

dependencies: pydantic, pyyaml, pandas, matplotlib, ortools

\[project.optional-dependencies].dev: ruff, black, mypy, pytest, pytest-cov, pre-commit, hypothesis



src-layout:



\[tool.setuptools]

package-dir = {"" = "src"}

\[tool.setuptools.packages.find]

where = \["src"]



Tool configs: \[tool.ruff], \[tool.black], \[tool.mypy], \[tool.pytest.ini\_options]



Criterion: pip install -e .\[dev] succeeds on a clean machine.



\### 4.2.2 — Pin dependency versions (semver with tilde)

Format: pydantic~=2.7, ruff~=0.6, mypy~=1.11, etc.



Criterion: identical installation locally and in CI.



\### 4.2.3 — Minimal smoke import test

tests/test\_imports.py:



def test\_imports():

&nbsp;   import opmed

&nbsp;   import opmed.solver\_core

&nbsp;   import opmed.dataloader



Criterion: pytest is green.



\## 4.3 (Must) Lint/format/hooks (ruff, black, mypy, pre-commit)



\### 4.3.1 — Pre-commit configuration

.pre-commit-config.yaml with hooks: black, ruff (with --fix), mypy, plus standard ones (trailing-whitespace, end-of-file-fixer, check-yaml, check-toml).

Execute: pre-commit install



Criterion: hooks trigger on commit.



\### 4.3.2 — Type strictness

\[tool.mypy]:



strict = true, ignore\_missing\_imports = true, exclude = "(data/|docs/|schemas/|infra/|scripts/)", python\_version = "3.11"



Criterion: mypy src/opmed runs without errors on stubs.



\### 4.3.3 — Code style document

docs/CODESTYLE.md: required type hints for public APIs, Google/Numpy-style docstrings.



Criterion: file exists and is consistent with linters.



\## 4.4 (Should) Basic CI (GitHub Actions)



\### 4.4.1 — Lint workflow: .github/workflows/lint.yml

Steps: checkout, setup-python 3.11, cache pip (hashFiles('pyproject.toml')), install -e .\[dev], run ruff, black --check, mypy src/opmed.

Criterion: workflow green on PR/main.



\### 4.4.2 — Tests workflow: .github/workflows/tests.yml

Steps: checkout, setup-python 3.11, cache pip, install, run pytest -q, upload coverage/junit artifacts (optional).

Criterion: tests pass, artifacts (coverage/junit) optionally uploaded.



\### 4.4.3 — Speed markers

In pyproject add:



\[tool.pytest.ini\_options]

addopts = "-q --cov=opmed --cov-report=term-missing"

testpaths = \["tests"]



Criterion: CI fast (<2–3 min), can exclude -m slow if necessary.



\## 4.5 (Could) Makefile (local management, without Docker)



\### 4.5.1 — Create Makefile with targets setup, lint, test, run, tune, clean

PYTHON ?= python

PKG = src/opmed



.PHONY: setup lint test run tune clean



setup:

&nbsp;	$(PYTHON) -m pip install --upgrade pip

&nbsp;	$(PYTHON) -m pip install -e .\[dev]

&nbsp;	pre-commit install



lint:

&nbsp;	ruff check .

&nbsp;	black --check .

&nbsp;	mypy $(PKG)



test:

&nbsp;	pytest



run:

&nbsp;	$(PYTHON) scripts/run.py \\

&nbsp;		--config configs/config.yaml \\

&nbsp;		--surgeries data/input/surgeries.csv \\

&nbsp;		--outdir data/output



tune:

&nbsp;	$(PYTHON) scripts/tune.py \\

&nbsp;		--config configs/config.yaml \\

&nbsp;		--grid configs/tune\_grid.yaml \\

&nbsp;		--outdir data/output/tune



clean:

&nbsp;	rm -rf .pytest\_cache .mypy\_cache .ruff\_cache .coverage



Criterion: all targets run. Under Windows PowerShell — make via mingw32-make/gmake or Invoke-Build; optionally add scripts/make.ps1.



\### 4.5.2 — Configs for run/tune

Folder configs/ (repo root):



config.yaml — keys from theory (ROOMS\_MAX, SHIFT\_MIN/MAX, …, solver params, TIME\_UNIT)

tune\_grid.yaml — grid for num\_workers, time\_limit, search\_branching



Criterion: yamllint in pre-commit passes (check-yaml hook).



\## 4.6 (Should) JSON schemas in schemas/ (use your folder)



\### 4.6.1 — Generation of Pydantic schemas

Define Pydantic models Surgery, Config, SolutionRow (stubs ok).

Script scripts/gen\_schemas.py: export model.model\_json\_schema() → schemas/{surgery.schema.json, config.schema.json, solution.schema.json}.

Add make target schemas (optional).



Criterion: schema files generated and valid JSON.
