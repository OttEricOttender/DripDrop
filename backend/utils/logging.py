"""Structured logging setup.

The backend writes JSON-friendly log lines so they can be ingested into any
log aggregator without parsing tricks. ``configure_logging`` is idempotent
and safe to call multiple times.
"""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s :: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Tone down chatty libraries.
    for noisy in ("uvicorn.access", "rasterio", "fiona"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
