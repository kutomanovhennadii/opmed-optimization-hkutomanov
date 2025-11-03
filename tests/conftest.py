import sys
from pathlib import Path

# Добавляем корень репозитория (где лежат scripts/, src/, Makefile)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
