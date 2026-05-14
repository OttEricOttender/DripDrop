# Architecture Decision Records

Lightweight ADRs. Each captures a decision, the alternatives, the
rationale, and the consequences. Newest at the bottom. Update an ADR's
status (rather than delete it) if a decision is later reversed.

---

## ADR-001 — Use FastAPI, not Flask

**Status:** accepted (Phase 0)
**Context:** Legacy v0.1 of HydroCalc used Flask 3.0.3 with a single
`/coordinates` POST endpoint that subprocess-called delineate.py. The
customer's brief explicitly lists FastAPI.
**Decision:** Migrate to FastAPI. Keep Flask alive in parallel under
`app/` and on port 5001 until Phase 3 fully cuts over.
**Alternatives considered:** stay on Flask (rejected — diverges from
spec, weaker typing); migrate to Litestar (rejected — adds risk for no
documented benefit).
**Consequences:** Two services in `docker-compose.yml` during the
migration; doubled CI surface; clean Pydantic types throughout the new
code.

## ADR-002 — Use pysheds, not WhiteboxTools

**Status:** accepted (Phase 0)
**Context:** The customer's brief listed WhiteboxTools but the
two PDFs (`TÜ_projekt.pdf`, `TÜ_projekt_protsess.pdf`) both name pysheds
specifically. Legacy `scripts/delineate.py` already uses pysheds.
**Decision:** pysheds.
**Alternatives considered:** WhiteboxTools (rejected — would require
adding a Rust binary to the Docker image and migrating working code);
hybrid WBT-offline + pysheds-online (rejected — added complexity without
clear gain).
**Consequences:** No new system dependency. Behaviour preserved from
legacy. Pysheds' performance characteristics constrain per-catchment
size, which is fine because Phase 2 pre-clips to per-valgla extents.

## ADR-003 — All internal GIS in EPSG:3301 (L-EST97)

**Status:** accepted (Phase 0)
**Context:** Estonia's official engineering CRS is L-EST97. Mixing CRSs
in scientific code is one of the most common sources of subtle area /
distance errors.
**Decision:** Everything inside `backend/` and `gis/` is EPSG:3301.
EPSG:4326 lives only at the API boundary. `backend/gis/crs.py` is the
single source of CRS conversion; no other module instantiates a
`pyproj.Transformer`.
**Consequences:** Frontend payloads convert once on input and once on
output; internal area calculations are in m² (converted to km² at the
API edge); no risk of silent CRS drift between modules.

## ADR-004 — Pre-clip DEMs per official Vooluveekogude valgla, offline

**Status:** accepted (Phase 0)
**Context:** Estonia's national 5 m DTM is ~50 GB. Running sink-fill +
flow-dir + flow-acc on the full mosaic per request is infeasible. The
PDF explicitly suggests using the pre-existing Vooluveekogude valglad
to clip.
**Decision:** Offline `scripts/preprocess.py` clips the DTM into one
GeoTIFF per official valgla polygon, then runs sink-fill + flow-dir +
flow-acc per slice, storing results in `data/preprocessed/*` keyed by
KKR code. Runtime never re-runs flow-direction from raw DTM.
**Alternatives considered:** Full-Estonia COG + windowed reads
(rejected — more I/O per request, harder Docker volume shipping);
Maa-amet 1×1 km tiles (rejected — cross-tile watershed stitching is
non-trivial and risks edge artefacts).
**Consequences:** ~30 min one-off preprocessing per host. Runtime
catchment delineation is bounded in time and memory. The named Docker
volume `hydrocalc_preprocessed` persists across rebuilds.

## ADR-005 — q̄_k placeholder until customer ships raster

**Status:** accepted (Phase 1), pending customer follow-through
**Context:** Formula (1.1) requires the annual climatic drainage norm
cartogram. The customer has not provided it yet.
**Decision:** Use a hardcoded constant of 7.0 l/(s·km²), source of truth
in `backend/config.py:Settings.q_bar_k_placeholder_l_per_s_km2`. Every
output flagged `q_bar_k_source = "placeholder"`. Startup log emits a
prominent warning. PDF reports will carry a watermark in Phase 5.
**Alternatives considered:** Search Estonian hydrology literature for
the cartogram (rejected — risks using an unofficial source); block all
calculation until raster arrives (rejected — kills demo / dev velocity);
allow manual entry per request (rejected — non-reproducible, defeats
the purpose).
**Consequences:** Phase 1 + Phase 2 + Phase 3 can all proceed. Every
PDF report generated before the raster lands is non-defensible — must
be made obvious in the UI and report. Swapping in the raster is a
one-function change in `cartogram.py`.

## ADR-006 — Use log10 (not ln) in formulas 1.3 and 1.6

**Status:** accepted (Phase 1), pending written customer confirmation
**Context:** PDF writes `log(p+1)` without specifying base. Legacy
`scripts/calculations.py` uses `math.log10`. Estonian / Soviet empirical
hydrology (Pol'akov, Sokolovskij) conventionally uses log10.
**Decision:** log10.
**Alternatives considered:** ln (rejected — would silently shift all
peak-flow estimates).
**Consequences:** Worked example pinned in
`tests/test_hommik.py::TestComputeWorkedExample` agrees with the by-hand
calculation under this convention. Risk: if customer says "ln", every
historical output is wrong by a factor of `log10(p+1) / ln(p+1)`. Get
written sign-off before Phase 5 ships PDFs to engineers.

## ADR-007 — `a` parameter mapping = (ETAK 305 ∩ 306) + A_km

**Status:** accepted (Phase 1), confirmed verbally by user
**Context:** Formula (1.2) needs `a` = share of "võsastunud ja
metsastunud liigniiske mineraalmaa + kuivendatud madalsoo". ETAK has no
direct "liigniiske" (wet) tag.
**Decision:** Derive `a` as the spatial intersection of ETAK 305
(puittaimestik) with ETAK 306 (märgala), plus A_km. Surfaced in
`LandCoverBreakdown.a_wet_mineral_plus_akm` and documented in PDF
report as an assumption.
**Consequences:** The mapping is testable and reproducible. If the
customer has a soil-map-based definition we should switch to that,
bump `formula_revision`, and re-run any historical calculations.

## ADR-008 — Hommik calculator is pure (no I/O, no DB)

**Status:** accepted (Phase 1)
**Context:** Legacy `calculations.py` ran arithmetic on module-level
None values at import time — unusable. Mixing I/O with formulas makes
both untestable.
**Decision:** `backend/services/hommik.py` is a set of pure functions
plus an orchestrator that takes a Pydantic `HommikInputs` and returns
a Pydantic `HommikResult`. No file reads, no DB calls, no network.
**Consequences:** Unit-testable in milliseconds; deterministic;
swappable. The cartogram sampling lives separately in
`cartogram.py`; the GIS pipeline lives in Phase 2/3 services.

## ADR-009 — Reproducibility chain in every PDF report

**Status:** accepted (Phase 0), implemented partially
**Context:** The customer's brief lists legal defensibility as a top-5
priority. Engineering reports must be replayable years later.
**Decision:** Every `HommikResult` carries `formula_revision` and
`q_bar_k_source`. The PDF report footer (Phase 5) will additionally
embed the SHA-256 of `datasets.lock.json`. Bumping any formula constant
requires bumping `formula_revision`.
**Consequences:** Engineers + auditors can verify which input bytes and
formula version produced a given report. CI gets a reproducibility test
in Phase 6 that re-runs a known catchment and asserts byte-equal output.

## ADR-010 — Per-valgla rasters in a named Docker volume, not the image

**Status:** accepted (Phase 0)
**Context:** Per-valgla rasters total several GB. Baking them into the
image would make every `docker compose pull` very slow and hard to
update.
**Decision:** Named volume `hydrocalc_preprocessed`. Populated by
`scripts/preprocess.py` on first run via a one-shot job or manual
invocation.
**Consequences:** Image stays small. Preprocessing runs once per host.
Phase 6 adds a `docker compose run preprocessor` convenience entry.
