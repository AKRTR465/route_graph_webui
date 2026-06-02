from __future__ import annotations

import os

# Keep preview/render tests on a non-GUI backend so they stay local and stable on Windows.
os.environ.setdefault("MPLBACKEND", "Agg")
