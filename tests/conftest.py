import sys
from pathlib import Path

# (1) Add repository root to sys.path to enable absolute imports
#     The root directory contains scripts/, src/, and Makefile.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
