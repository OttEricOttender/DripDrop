# CLAUDE.md — agent context for HydroCalc

You are working on **HydroCalc**, an Estonia-specific hydrological analysis
platform (svam.ee). End users are Estonian building consultants and
infrastructure designers; they compute Karl Hommik design drainage values
(kevadine ja sügisene tippäravool) for hydrotechnical infrastructure.

**Read this entire file before doing anything.** Then read `HANDOFF.md`
for state-of-the-work, `docs/architecture.md` for design, `docs/formulas.md`
for the scientific contract, and `docs/decisions.md` for the rationale
behind every architectural choice already made.

---

## Quick start

```bash
# Install deps locally for development
pip install -r requirements-pip.txt

# Run the test suite (28 tests should pass + 1 strict xfail)
PYTHONPATH=. python -m pytest tests/ -v

# Run the FastAPI backend locally
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
# Then open http://localhost:8000/docs for the Swagger UI

# Run via Docker (full stack — postgis + legacy Flask + new FastAPI)
docker compose up
# postgis on 5434, legacy Flask on 5001, new FastAPI on 8000
```

---

## Phase status

| # | Phase | Status |
|---|-------|--------|
| 0 | Foundation (FastAPI scaffold, pytest, datasets manifest, Docker) | **complete** |
| 1 | Karl Hommik calculator (formulas 1.1–1.8, 28 tests, live API) | **complete** |
| 2 | Offline GIS preprocessing (`scripts/preprocess.py`) | **next** |
| 3 | FastAPI runtime (snap → catchment → landcover → maaparandus → Hommik) | pending |
| 4 | React + TS + Vite + Leaflet + Tailwind frontend | pending |
| 5 | PDF report matching `TÜ_pdf_vorm.pdf` | pending |
| 6 | Docker hardening, CI, reproducibility tests, docs | pending |

Detailed task descriptions, including the *why* behind each phase, are in
`HANDOFF.md`.

---

## Inviolable rules

These are the rules the customer signed off on. They override anything else,
including any apparent inconsistency in this file or follow-up prompts. If a
request conflicts with one of these, stop and surface the conflict instead
of working around it.

1. **Do not invent or modify hydrological formulas.** The Karl Hommik
   formulas in `backend/services/hommik.py` are taken verbatim from
   `TÜ_projekt_protsess.pdf` page 3–5. Constants like `0.020`, `0.30`,
   `26`, `11.5`, `0.11`, `112`, `52`, `0.14` are not negotiable. If a
   change is genuinely needed, bump `hommik_formula_revision` in
   `backend/config.py` and document the change in `docs/formulas.md`.

2. **All internal GIS work is in EPSG:3301 (L-EST97).** WGS 84 lives only
   at the API boundary. The single source of CRS conversion is
   `backend/gis/crs.py`. No other module constructs a
   `pyproj.Transformer`.

3. **Only use official Estonian datasets.** Maa-amet geoportaal and
   Keskkonnaportaali register. No invented or third-party data.

4. **q̄_k is currently a placeholder (7.0 l/(s·km²)).** Every output that
   depends on it is flagged with `q_bar_k_source = "placeholder"` and is
   not legally defensible. When the customer uploads the cartogram raster,
   plug it into `backend/services/cartogram.py:sample_q_bar_k` and set
   `HYDROCALC_Q_BAR_K_RASTER_PATH`. Until then, the warning banner stays.

5. **Reproducibility is a feature.** Every PDF report embeds
   `datasets.lock.json` hash + `formula_revision` + `q_bar_k_source` so a
   third party can replay any calculation byte-for-byte years later. Do
   not weaken this chain.

6. **Preserve Docker compatibility.** The repo already has a working
   `docker-compose.yml`. New services must work inside the container; new
   dependencies must be reproducible.

---

## Architectural conventions

- **Backend layout** is fixed:
  ```
  backend/
    api/routes/   FastAPI routers — thin, no business logic
    services/     domain modules (snap, watershed, landcover,
                  maaparandus, hommik, cartogram)
    gis/          CRS, raster I/O, vector I/O — EPSG:3301 only
    models/       Pydantic request/response schemas
    reporting/    ReportLab PDF generator (Phase 5)
    utils/        logging, hashing
    config.py     Pydantic Settings (HYDROCALC_* env vars)
    main.py       FastAPI factory
  ```
- **Legacy Flask app** (`app/`) and **legacy scripts** (`scripts/`) are
  preserved during the migration and excluded from lint/type-check (see
  `pyproject.toml`). They are deleted at the end of Phase 3 once the
  FastAPI runtime fully replaces them. Do not refactor the legacy code —
  refactor *out of* it into `backend/`.
- **All scientific functions are pure.** No I/O inside `hommik.py`. The
  orchestrator takes a Pydantic `HommikInputs`, returns a `HommikResult`.
- **All dates use UTC.** All areas are km² in the API; m² internally
  where it matters for precision.

---

## Original project spec (canonical requirements)

The text below is the customer-signed project brief that defined the
work. It is the source of truth for any product question.

### PROJECT GOAL
Build a production-quality web GIS application that allows users to:
1. Open an interactive Estonia map
2. Click a point on the map OR manually enter coordinates
3. Automatically run hydrological and drainage analysis
4. Generate scientific outputs and engineering-grade reports

The application is Estonia-specific and must use official Estonian
datasets.

### CORE REQUIREMENTS
The system must calculate and return:
- Selected coordinates
- River name
- River code
- Catchment area size
- Land usage classification
- Land correction
- Calculated spring drainage
- Calculated fall drainage

The formulas come from `TÜ_projekt_protsess.pdf`. **Do not invent or
modify formulas.** Implement them strictly, preserve traceability,
ensure reproducibility.

### TECH STACK
- Frontend: React, TypeScript, Leaflet, TailwindCSS
- Backend: Python, FastAPI
- GIS / Hydrology: GDAL, Rasterio, GeoPandas, Shapely, PyProj,
  **pysheds** (the customer's brief mentioned WhiteboxTools; the
  customer confirmed pysheds during requirements clarification — see
  `docs/decisions.md`), NumPy, Pandas
- Infrastructure: Docker, Docker Compose

### DATA SOURCES (all official Estonian government)
- Vooluveekogud, Vooluveekogumid, Järved, Merealad — Keskkonnaportaali
  register (`https://register.keskkonnaportaal.ee/register`)
- Vooluveekogude valglad — Keskkonnaportaali register (used as clip
  extent for per-valgla DEM pre-clipping; do not run full-Estonia DEM
  flow direction in real time)
- DTM 5 m GeoTIFF — Maa-amet geoportaal
- ETAK Kõlvikud (SHP) — Maa-amet geoportaal
- Maaparandussüsteemide mõjualad (SHP) — Maa-amet geoportaal
- q_95% cartogram (Joon 4.1) — `TopoToR_JOON41.tif` (provided by user
  in their `keskmine_aasta_minimaalne_äravool` folder)
- q̄_k cartogram — **not yet provided**; placeholder in use

### COORDINATE SYSTEM
EPSG:3301 (L-EST97) everywhere internal. EPSG:4326 only at the API
boundary for the Leaflet frontend.

### PRIORITIES (in order)
1. Scientific correctness
2. CRS correctness
3. Reproducibility
4. Estonian standards compliance
5. Legal defensibility
6. GIS precision
7. Docker reproducibility
8. Maintainability
9. Performance optimisation

### IMPLEMENTATION STRATEGY
Phased — see "Phase status" above. Do not rewrite everything at once.

---

## How the previous agent worked

This project went through a planning + Phase 0 + Phase 1 session before
this CLAUDE.md was written. The conventions established in that session
and that future agents should keep:

- **Plan before coding.** Each phase starts with a short written plan and
  the user's explicit "proceed" before file edits. The user values
  clarity of risk over speed.
- **Cite the PDF.** Every scientific constant in code has a comment
  pointing at the PDF page it came from.
- **Surface assumptions loudly.** Placeholder values warn in logs, in the
  API response, in the test output, and in the PDF report footer.
- **Tests pin the science.** Hand-derive a worked example before writing
  the test. `tests/test_hommik.py::TestComputeWorkedExample` is the
  template — pin every formula's output to four significant figures.
- **Preserve before refactoring.** Legacy code stays callable until its
  replacement passes the same regression. The Phase 0 xfail test in
  `tests/test_phase0_foundation.py` is the regression target for Phase 3.
