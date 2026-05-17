"""GIS constants shared across backend services.

These values must stay in sync with scripts/preprocess.py (which uses its own
copies so the preprocessing script has no dependency on backend/).  If either
is changed, update both.
"""

from __future__ import annotations

# D8 flow direction encoding (clockwise from N):
# N=64, NE=128, E=1, SE=2, S=4, SW=8, W=16, NW=32
# Matches pysheds default and scripts/preprocess.py:DIRMAP.
DIRMAP: tuple[int, ...] = (64, 128, 1, 2, 4, 8, 16, 32)

# Minimum upstream cell count to classify a cell as a stream.
# 500 cells × 25 m² (5 m pixel) = 12 500 m² ≈ 0.01 km².
FLOW_ACC_THRESHOLD: int = 500
