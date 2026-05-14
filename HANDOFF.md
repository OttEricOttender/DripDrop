# HANDOFF — HydroCalc state of the work

This document is the bridge from the Phase 0 + Phase 1 work done in
Claude Cowork to the Phase 2+ work that will be done in Claude Code.
It captures **what** has been built, **why** each non-obvious decision
was made, and **what the next agent should do first**.

For canonical rules and the project spec, read `CLAUDE.md`.
For architecture, read `docs/architecture.md`.
For formulas + their worked example, read `docs/formulas.md`.
For the rationale behind every architectural choice, read `docs/decisions.md`.

---

## State summary

* **Repo:** master branch, ahead of `origin/master` by zero commits — the
  Phase 0 + 1 work has **not yet been committed**. The first thing the
  next agent should do is review and commit it (suggested commits below).
* **Backend:** new FastAPI app under `backend/`, scaffold + Karl Hommik
  calculator live. `POST /api/hommik/calculate` returns a verified
  worked example.
* **Tests:** 28 passing + 1 strict `xfail` that locks in the legacy
  `scripts/calculations.py` bug as the Phase 3 regression target.
* **Docker:** `backend-service` added to `docker-compose.yml` (port 8000)
  alongside the legacy `main-service` (port 5001) and `database-service`
  (postgis on 5434). The new service uses a named volume
  `hydrocalc_preprocessed` to hold the per-valgla rasters Phase 2 will
  generate.
* **Legacy code:** `app/` (Flask) and `scripts/` (delineate.py,
  calculations.py) are untouched and still working. They will be
  deleted at the end of Phase 3.

## What's NOT done yet

* Phase 2 — offline GIS preprocessing pipeline (`scripts/preprocess.py`).
  This is the next phase and the most data-sensitive one.
* Phase 3 — wiring snap → catchment → landcover → maaparandus → Hommik
  into a `POST /api/analyze` route.
* Phase 4 — React + TS + Leaflet + Tailwind frontend.
* Phase 5 — PDF report following `TÜ_pdf_vorm.pdf` exactly.
* Phase 6 — Docker hardening, CI, reproducibility tests, deployment docs.

---

## Confirmed decisions (user signed off in chat)

These four blocked Phase 0 from starting. Carry them forward as
constraints — do not re-litigate without checking with the user.

| # | Question | Decision | Implication |
|---|----------|----------|-------------|
| 1 | Where is the existing codebase? | GitHub: `https://github.com/OttEricOttender/HydroCalc` | Brownfield. Preserve `app/` and `scripts/` until Phase 3 cuts over. |
| 2 | How to source q̄_k cartogram? | **User provides raster later.** Until then, use a hardcoded placeholder (7.0 l/(s·km²)) with prominent flagging. | `backend/services/cartogram.py:sample_q_bar_k` returns placeholder by default. Every output carries `q_bar_k_source` flag. |
| 3 | pysheds vs WhiteboxTools? | **pysheds** — matches both PDF references. | All watershed logic in `backend/services/watershed.py` uses pysheds. Don't introduce WBT. |
| 4 | DEM strategy? | **Pre-clip per official Vooluveekogude valgla**, offline, idempotent, in a named Docker volume. | Phase 2 builds this. Runtime never re-runs sink-fill from raw DTM. |
| 5 | Flask → FastAPI? | **Migrate now**, keep Flask alive in parallel until Phase 3 cutover. | Phase 0 set up FastAPI; legacy Flask still works at port 5001 for Cypress tests. |

## Open questions for the user

These need answers before the corresponding work can be finalised.
Don't block on them — push the design assumption and surface the
question; the user will resolve when they have time.

1. **q̄_k raster file** — when and where. Until it lands, every PDF
   report carries a "non-defensible" watermark.
2. **`a` parameter mapping confirmation.** Phase 0 documented `a =
   (ETAK 305 ∩ 306) + A_km`. User confirmed verbally during Phase 0
   planning. Re-confirm before Phase 3 ships, since this is the only
   place ETAK semantics required interpretation.
3. **`log` vs `log10` in formulas 1.3 and 1.6.** Legacy code uses
   `log10`; HydroCalc follows that. Customer confirmation in
   writing would be ideal — see `docs/decisions.md` ADR-006.
4. **PDF report watermark text for placeholder mode.** Wording for
   "this report uses placeholder q̄_k" — drafted in `docs/formulas.md`
   but final copy should come from the customer.

---

## Architecture in one paragraph

The frontend (Leaflet, EPSG:4326) posts a coordinate to FastAPI. The
backend converts once via `backend/gis/crs.py`, looks up which official
valgla polygon contains the point, loads the corresponding pre-clipped
DEM / flow-dir / flow-acc grids from
`data/preprocessed/<kkr>.tif`, runs pysheds catchment delineation, then
intersects the catchment polygon with the pre-loaded `kolvikud.fgb`,
`maaparandus.fgb`, and the two cartogram rasters. The results feed the
Karl Hommik calculator (`backend/services/hommik.py`), which returns a
`HommikResult` with full provenance. The PDF generator (Phase 5) embeds
this plus the `datasets.lock.json` hash so any third party can replay
the calculation.

## Files map

```
HydroCalc/
├── CLAUDE.md            agent context — read first
├── HANDOFF.md           this file — read second
├── README.md            user-facing readme
├── pyproject.toml       ruff/black/mypy/pytest config + project metadata
├── requirements-pip.txt FastAPI + Hommik runtime deps
├── requirements-conda.txt   GDAL-heavy GIS deps (unchanged)
├── docker-compose.yml   three services: db, legacy flask, new fastapi
├── docker/
│   ├── db/Dockerfile        postgis (unchanged)
│   ├── main/Dockerfile      legacy flask (unchanged)
│   └── backend/Dockerfile   new fastapi (added Phase 0)
├── backend/
│   ├── __init__.py
│   ├── main.py              FastAPI factory + lifespan
│   ├── config.py            Pydantic Settings
│   ├── api/routes/
│   │   ├── health.py        GET /healthz
│   │   └── hommik.py        POST /api/hommik/calculate, GET /api/hommik/cartogram-status
│   ├── services/
│   │   ├── hommik.py        Karl Hommik formulas — DO NOT MODIFY constants
│   │   └── cartogram.py     placeholder q̄_k / q_95% sampling
│   ├── gis/crs.py           single CRS transformer (EPSG:3301 ↔ EPSG:4326)
│   ├── models/schemas.py    Pydantic schemas — public API contract
│   ├── reporting/           empty (Phase 5)
│   └── utils/
│       ├── logging.py
│       └── hashing.py       sha256_file / sha256_bytes
├── tests/
│   ├── conftest.py
│   ├── test_phase0_foundation.py    boots FastAPI, locks legacy bug as xfail
│   ├── test_hommik.py               22 unit + integration tests for the calculator
│   └── test_api_hommik.py           3 FastAPI integration tests
├── docs/
│   ├── architecture.md      system design + CRS policy
│   ├── formulas.md          full Hommik reference + worked example
│   └── decisions.md         ADR log of every architectural choice
├── data/
│   ├── .gitkeep
│   └── datasets.lock.json   manifest scaffold (populated in Phase 2)
├── app/                     LEGACY Flask — keep working, delete in Phase 3
├── scripts/                 LEGACY delineate.py / calculations.py — same
└── Documentation/           original team docs (iterations 1–4)
```

---

## Phase 2 work plan — read carefully before starting

### Goal
Build `scripts/preprocess.py` — an idempotent, deterministic, offline
script that produces every piece of GIS data the runtime needs.

### Inputs (downloads)
| Dataset | Source | Filename |
|---------|--------|----------|
| Vooluveekogud (SHP) | Keskkonnaportaali register: Vesi > Veekogud > Vooluveekogud | `vooluveekogud.shp` |
| Vooluveekogumid (SHP) | Keskkonnaportaali register: Vesi > Veekogumid > Vooluveekogumid | `vooluveekogumid.shp` |
| Järved, Merealad (SHP) | Keskkonnaportaali register: Vesi > Veekogud > Järved, Merealad | `seisuveekogud.shp` |
| Vooluveekogude valglad (SHP) | Keskkonnaportaali register: Vesi > Vesikonnad ja valgalad > Vooluveekogude valglad | `valglad.shp` |
| ETAK Kõlvikud (SHP) | Maa-amet ETAK: `https://geoportaal.maaamet.ee/.../Laadi-ETAK-andmed-alla-p609.html` | `kolvikud.shp` |
| Maaparandussüsteemide mõjualad (SHP) | Maa-amet kitsendused: `https://geoportaal.maaamet.ee/.../Kitsenduste-andmete-allalaadimine-p624.html` | `maaparandus.shp` |
| DTM 5 m GeoTIFF | Maa-amet: `https://geoportaal.maaamet.ee/.../Laadi-korgusandmed-alla-p614.html` | `DTM_5m_eesti.tif` |
| q_95% cartogram | provided by user (`/Users/.../keskmine_aasta_minimaalne_äravool/TopoToR_JOON41.tif`) | `q95.tif` |
| q̄_k cartogram | **not yet provided** | placeholder until then |

### Pipeline steps (each must be a separate, testable function)

1. `download_dataset(name) -> Path` — fetch + verify sha256 against a
   pinned hash. If the hash isn't pinned yet, record it and write into
   `datasets.lock.json`. Fail loudly if a mismatch happens later.
2. `reproject_to_lest97(path) -> Path` — convert every vector + raster
   layer to EPSG:3301. Skip if already in 3301.
3. `build_river_index(rivers_path) -> rivers.fgb + spatial_index` —
   FlatGeoBuf format for fast bbox queries; R-tree built at preprocess
   time.
4. `for each valgla polygon: clip_dem(valgla, dem_path)` →
   `data/preprocessed/dem/<kkr>.tif`. Use rasterio masked windows so
   memory stays bounded.
5. `for each clipped DEM: sink_fill + flowdir + flowacc` (pysheds) →
   `data/preprocessed/flowdir/<kkr>.tif`,
   `data/preprocessed/flowacc/<kkr>.tif`. Same pysheds parameters that
   `scripts/delineate.py` already uses, so behaviour is preserved.
6. `vectorize_streams(flowacc) -> streams.fgb` for the snap step.
7. `emit_manifest()` — write `datasets.lock.json` with every entry:
   name, source_url, sha256, retrieved_at (ISO 8601 UTC), crs,
   resolution, output_path. Manifest schema is in
   `data/datasets.lock.json` (scaffold already exists).

### Idempotency & determinism
- Each step skips if the output exists AND its sha256 matches the
  manifest. Use `--force` to rebuild.
- Set `numpy.random.seed(0)` only inside any pysheds call that requires
  it; the rest of the pipeline is deterministic by construction.
- Use UTC timestamps.

### Performance budget
- Whole pipeline runs once per host, takes ~30 minutes on a reasonable
  machine. Acceptable.
- Per-valgla clip + sink-fill + flow-acc fits in 4 GB RAM for the
  largest catchment (Pärnu, ~6 700 km²). Validate on Emajõgi (~9 800 km²)
  as the upper bound.

### Testing
- Unit tests with a tiny synthetic 100×100 cell DEM fixture (commit it
  to `tests/fixtures/`) that exercises sink-fill + flow-dir + flow-acc.
- Integration test against a small real catchment downloaded inside CI
  (~1 minute total runtime).
- `datasets.lock.json` round-trip test (write → read → assert equal).

### Open questions before Phase 2 starts
- Where to host the preprocessed bundle for CI? Suggestion: GitHub
  Releases with the sha256 in `datasets.lock.json` so CI downloads the
  same bytes every run.
- Should we use Cloud-Optimised GeoTIFF (COG) for the DEM clips? Yes —
  pysheds reads them fine, and the runtime windows are smaller.

---

## What the next agent should do, in order

1. **`git status` + read this file end-to-end + read `CLAUDE.md`** before
   touching anything.
2. **Commit Phase 0 + Phase 1** (the user asked for this in chat but the
   transition happened before the commit). Suggested splits:
   - Commit A: `chore: add .gitignore for new dirs + remove stray .DS_Store`
   - Commit B: `feat(backend): Phase 0 — FastAPI scaffold, Pydantic schemas, CRS module, tests`
   - Commit C: `feat(backend): Phase 1 — Karl Hommik calculator + live API + worked example`
   - Commit D: `docs: add CLAUDE.md, HANDOFF.md, architecture.md, formulas.md, decisions.md`
3. **Run the test suite** (`PYTHONPATH=. python -m pytest tests/ -v`) and
   confirm 28 pass + 1 xfail.
4. **Boot uvicorn locally** and hit `http://localhost:8000/docs` to
   confirm the live API works. Try the worked example payload to ensure
   you get `Q_kev_max_m3_per_s ≈ 7.377` and `Q_veg_max_m3_per_s ≈ 3.934`.
5. **Start Phase 2** following the work plan above. Before writing
   `scripts/preprocess.py`, write the unit tests with the synthetic DEM
   fixture so the implementation has a target.

---

## Glossary (Estonian → English)

| Estonian | English | Where in code |
|----------|---------|---------------|
| valgala | catchment / watershed | `CatchmentInfo` |
| valglad (pl.) | catchments / watersheds | `valglad.shp` |
| vooluveekogu | flowing watercourse | `RiverInfo` |
| seisuveekogu | standing waterbody (lake, sea) | `seisuveekogud.shp` |
| peajõed | main rivers | rendered with thicker line weight |
| lisajõed | tributaries | rendered with thinner line weight |
| arvutusäravool | design drainage | `HommikResult.Q_*_max_m3_per_s` |
| äravoolunorm | drainage norm | `q_bar` |
| kartogramm | cartogram | `cartogram.py` |
| madalsoo | low-bog / fen | ETAK 306-10 |
| raba | bog | ETAK 306-20 |
| õõtsik | quaking bog | ETAK 306-30 |
| soovik | mire transition | ETAK 306-40 |
| maaparandus | land improvement system (drained) | `maaparandus.shp` |
| kõlvikud | land-use parcels | ETAK |
| ületõusutõenäosus | exceedance probability | `p_percent` |
| kevadine | spring (season) | `q_kev_max` |
| sügisene | autumn (season) | `q_veg_max` |
| tippäravool | peak drainage | `q_*_max` |
| moodulkoefitsient | modular coefficient | `k95` |
