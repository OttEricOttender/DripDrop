"""SHA-256 helpers used by ``datasets.lock.json`` and the PDF footer.

Hashing is part of HydroCalc's legal-defensibility story: every input
dataset is hashed at preprocessing time so a calculation can be replayed
years later from the same bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

_BLOCK = 1 << 20  # 1 MiB


def sha256_file(path: Path) -> str:
    """Return the hex SHA-256 of a file."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(_BLOCK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
