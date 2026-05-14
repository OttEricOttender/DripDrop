# HydroCalc — Estonia-specific hydrological analysis platform (svam.ee)

HydroCalc lets Estonian building consultants and infrastructure designers
compute Karl Hommik design drainage values (kevadine ja sügisene tippäravool)
for any point on the country's official watercourse network, using
authoritative Estonian datasets (Maa-amet, Keskkonnaportaal).

## Status

HydroCalc is mid-migration from a Flask + vanilla-JS prototype (v0.1.x,
delivered as a student project iteration 1–4) into a production-grade
FastAPI + React + TypeScript application (v0.2.0+). The migration is
phased so the existing demo never goes dark.

| Phase | Description | Status |
|------:|-------------|--------|
| 0 | Repo into workspace, FastAPI scaffold, pytest baseline | in progress |
| 1 | Karl Hommik calculator (pure functions, unit tests) | pending |
| 2 | Offline GIS preprocessing (`scripts/preprocess.py`) | pending |
| 3 | FastAPI runtime (snap → catchment → landcover → maaparandus → Hommik) | pending |
| 4 | React + TS + Leaflet + Tailwind frontend | pending |
| 5 | PDF report matching `TÜ_pdf_vorm.pdf` | pending |
| 6 | Docker, CI, reproducibility tests, docs | pending |

See [`docs/architecture.md`](docs/architecture.md) for the design.

## Repository layout

```
backend/        new FastAPI application (v0.2.0+)
frontend/       new React + TS + Vite + Leaflet UI                  (Phase 4)
gis/            offline GIS preprocessing modules                   (Phase 2)
app/            LEGACY Flask app — removed at end of Phase 3
scripts/        LEGACY delineate/calc scripts — refactored into backend/services
data/           raw + preprocessed datasets + datasets.lock.json manifest
docs/           architecture, datasets, formulas, reproducibility
docker/         Dockerfiles (db, main legacy, backend new)
tests/          pytest suite — unit, GIS integration, reproducibility
cypress/        LEGACY Cypress E2E tests — ported to Playwright in Phase 4
Documentation/  original team documentation (Iterations 1–4)
```

## Running the new FastAPI backend (local dev)

```bash
pip install -r requirements-pip.txt
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
curl http://localhost:8000/healthz
```

You should see a startup warning until you provide the q̄_k cartogram raster:

> q_bar_k cartogram raster is NOT configured; using placeholder value 7.000 l/(s·km²).
> Outputs will be flagged as non-defensible until the raster is provided.

## Running via Docker

```bash
docker compose up backend-service
# legacy Flask service still available at port 5001 during the migration:
docker compose up main-service
```

## Running tests

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

## Reproducibility

Every PDF report embeds `datasets.lock.json` hash + `formula_revision` +
the q̄_k source flag (`raster` or `placeholder`) so any calculation can
be replayed years later from the same bytes.

## Legacy docs (iterations 1–4)

* [DOCKER_instructions.md](DOCKER_instructions.md) — Iteration 4 Docker setup
* [Documentation/Use Cases](Documentation/Use%20Cases) — original UI prototypes
* [Documentation/Scope.md](Documentation/Scope.md) — original scope
* [Documentation/Project_Vision.md](Documentation/Project_Vision.md) — original vision
