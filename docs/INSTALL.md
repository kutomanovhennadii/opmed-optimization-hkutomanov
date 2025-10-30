# Setup & Installation


## Requirements

- Python 3.11+
- Poetry 1.8+ (https://python-poetry.org)
- Git

## Setup (Windows, PowerShell)

1. Clone the repository:
   git clone https://github.com/<your-account>/opmed-optimization.git
   cd opmed-optimization

2. Install Poetry (once per machine):
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -3.11
   poetry --version

3. Create the environment and install dependencies:
   py -3.11 -m poetry install

4. Activate local environment and ensure Poetry is on PATH:
   .\activate.ps1

5. (Optional) Enable Git hooks:
   poetry run pre-commit install

6. Smoke checks:
   poetry run python -c "import opmed"
   poetry run mypy src/opmed
   poetry run pytest -q

7. (Optional) Install `make` for running project targets:
   - **PowerShell as Administrator** → run:
     ```powershell
     choco install make -y
     ```
     If Chocolatey reports a lock-file or permission error, remove
     `C:\ProgramData\chocolatey\lib\make` and retry.
   - Alternative (non-admin): open **Git Bash** and use built-in `make`.

8. CLI placeholders:
   poetry run python scripts\run.py --help
   poetry run python scripts\tune.py --help

## Setup (Linux/macOS)

1. Clone the repository:
   git clone https://github.com/<your-account>/opmed-optimization.git
   cd opmed-optimization

2. Install Poetry:
   # see https://python-poetry.org/docs/#installation
   poetry --version

3. Create the environment and install dependencies:
   poetry install

4. Activate helper (prints how to run commands via Poetry):
   .\activate.sh

5. (Optional) Enable Git hooks:
   poetry run pre-commit install

6. Smoke checks:
   poetry run python -c "import opmed"
   poetry run mypy src/opmed
   poetry run pytest -q

7. (Optional) Install `make` if missing:
   ```bash
   sudo apt install make        # Ubuntu/Debian
   sudo dnf install make        # Fedora
   brew install make            # macOS (Homebrew)

8. CLI placeholders:
   poetry run python scripts/run.py --help
   poetry run python scripts/tune.py --help

## Notes

- Strict typing (mypy strict) and formatting (ruff + black) are enforced.
- If committing from Microsoft Visual Studio UI appears to hang, run `pre-commit run --all-files` from a terminal; CI will enforce checks on PRs.
