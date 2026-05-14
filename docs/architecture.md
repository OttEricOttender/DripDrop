# HydroCalc architecture

This document is the high-level map of the system as it stands at the end of
**Phase 0** (foundation). It will be updated at the end of each phase.

## Goal

A production-grade Estonia-only web GIS application that, given a point on the
map or a pair of coordinates, returns the Karl Hommik design drainage values
(kevadine ja sügisene tippäravool) along with the catchment, land-cover, and
maaparandus breakdown, and renders a downloadable PDF report. End users are
Estonian building consultants (*ehitusnõunikud*) and infrastructure designers.

## Domains

```
┌──────────────────┐    HTTPS    ┌────────────────────────────────────────┐
│ React + Leaflet  │──────────▶│ FastAPI                                  │
│ (EPSG:4326 UI)   │           │  api/   routes (analyze, rivers, report) │
└──────────────────┘           │  services/ snap, watershed, landcover,   │
                                │            maaparandus, hommik           │
                                │  gis/   CRS, raster, vector helpers      │
                                │  reporting/ ReportLab PDF                │
                                └────────────────┬───────────────────────┘
                                                 │
                                       reads ▼   │   ▲ reads
                                                 │   │
                              ┌──────────────────┴───┴──────────────────┐
                              │ /data/preprocessed/  (EPSG:3301, COGs,   │
                              │  per-valgla DEM / flow-dir / flow-acc,   │
                              │  vectorised streams, ETAK, maaparandus,  │
                              │  cartogram rasters)                       │
                              └──────────────────────────────────────────┘
                                                 ▲
                                                 │ written by
                                                 │
                                ┌──────────────────────────────────┐
                                │ scripts/preprocess.py             │
                                │ (offline, idempotent, lock-file)  │
                                └──────────────────────────────────┘
```

## CRS policy

* Every spatial operation inside `backend/` runs in **EPSG:3301** (L-EST97),
  Estonia's official engineering CRS. Areas are computed in metres² and
  converted to km² at the API boundary only.
* The Leaflet frontend uses **EPSG:4326** for tile rendering. Coordinates
  travel as WGS 84 through the API, are converted to L-EST97 in
  `backend/gis/crs.py` once, and stay in L-EST97 until they leave again.
* `backend/gis/crs.py` is the single place that constructs a
  `pyproj.Transformer`. No other module is allowed to.

## Reproducibility

Every PDF report carries:

1. The full `datasets.lock.json` SHA-256 hash, listing every input dataset
   with its source URL, sha256, retrieval timestamp, and CRS.
2. The `formula_revision` constant from `backend/config.py`. Changing
   any Hommik formula MUST bump this constant.
3. The `q_bar_k_source` flag (`raster` or `placeholder`). Reports
   generated with the placeholder are watermarked accordingly.
4. The exact snapped pour-point coordinates in both L-EST97 and WGS 84.

These four together let any third party rebuild the calculation byte-for-byte
years later — the reproducibility test suite (Phase 6) enforces it on CI.

## Phase status

| Phase | Description | Status |
|------:|-------------|--------|
| 0 | Repo into workspace, FastAPI scaffold, pytest baseline | in progress |
| 1 | Karl Hommik calculator (pure functions, unit tests) | pending |
| 2 | Offline GIS preprocessing (`scripts/preprocess.py`) | pending |
| 3 | FastAPI runtime (snap → catchment → landcover → maaparandus → Hommik) | pending |
| 4 | React + TS + Leaflet + Tailwind frontend | pending |
| 5 | PDF report matching `TÜ_pdf_vorm.pdf` | pending |
| 6 | Docker, CI, reproducibility tests, docs | pending |

## Legacy code

The original Flask app (`app/`) and the original delineation scripts
(`scripts/`) are preserved during the migration. They are excluded from
the new lint/type-check configurations (`pyproject.toml`) and will be
deleted at the end of Phase 3 once the FastAPI runtime fully replaces
them. Their existing Cypress tests will be ported to Playwright in Phase 4.
