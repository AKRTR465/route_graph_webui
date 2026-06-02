from __future__ import annotations

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Keep preview/render tests on a non-GUI backend so they stay local and stable on Windows.
os.environ.setdefault("MPLBACKEND", "Agg")
