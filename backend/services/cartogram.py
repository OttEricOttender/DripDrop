"""Cartogram sampling — q̄_k and q_95% at a point.

Two values feed the Hommik formulas (1.1) and (1.2):

* **q̄_k** — annual climatic drainage norm, sampled from a Maa-amet cartogram.
* **q_95%** — 95%-probability minimum average annual drainage modulus,
  sampled from cartogram *Joon 4.1* (file ``TopoToR_JOON41.tif``).

This module owns the lookup. Phase 1 only wires the placeholder code
path so the Hommik calculator can run end-to-end; the raster sampling
implementation lands in Phase 2 when ``scripts/preprocess.py`` copies
the cartograms into ``data/preprocessed/`` with verified checksums.

Until then, q̄_k falls back to the constant in ``backend.config`` and
q_95% must be supplied by the caller (the Phase 1 API endpoint accepts
it explicitly so we can demo end-to-end without GIS dependencies).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CartogramSample:
    value_l_per_s_km2: float
    source: Literal["raster", "placeholder"]
    raster_path: Path | None


def sample_q_bar_k(x_lest97: float, y_lest97: float) -> CartogramSample:
    """Return q̄_k at the given L-EST97 coordinate.

    Phase 1 always returns the placeholder; Phase 2 will replace the body
    with a rasterio-based sampler once the customer uploads the raster.
    """
    settings = get_settings()
    if settings.q_bar_k_raster_path is None:
        return CartogramSample(
            value_l_per_s_km2=settings.q_bar_k_placeholder_l_per_s_km2,
            source="placeholder",
            raster_path=None,
        )

    # Phase 2 will plug in rasterio here. Kept as an explicit error so we
    # can't accidentally claim "raster" provenance with no implementation.
    raise NotImplementedError(
        "q_bar_k raster sampling is implemented in Phase 2 "
        "(scripts/preprocess.py + backend.services.cartogram). Phase 1 only "
        "supports the placeholder path."
    )


def sample_q95(
    x_lest97: float, y_lest97: float, *, fallback: float | None = None
) -> CartogramSample:
    """Return q_95% at the given L-EST97 coordinate.

    Phase 1 returns the supplied ``fallback`` (taken from the API request
    body) so the calculator can be exercised without preprocessed data.
    Phase 2 samples ``data/preprocessed/q95.tif`` directly.
    """
    if fallback is None:
        raise ValueError(
            "q_95% raster sampling is implemented in Phase 2. "
            "Provide `fallback=` (l/(s·km²)) explicitly until then."
        )
    return CartogramSample(value_l_per_s_km2=fallback, source="placeholder", raster_path=None)
