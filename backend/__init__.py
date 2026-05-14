"""HydroCalc backend package.

The backend is structured as:
    backend/
        api/         FastAPI routers (thin HTTP layer)
        services/    domain logic (snap, watershed, landcover, maaparandus, hommik)
        gis/         CRS, raster I/O, vector I/O helpers (EPSG:3301 everywhere)
        models/      Pydantic request/response schemas
        reporting/   PDF report generation (matches TÜ_pdf_vorm.pdf)
        utils/       cross-cutting helpers (logging, hashing, caching)

Hard rules enforced project-wide:
    * Everything inside ``backend`` operates in EPSG:3301 (L-EST97).
    * CRS conversion happens only at the API boundary, via ``backend.gis.crs``.
    * Scientific formulas live in ``backend.services.hommik`` and MUST match the
      formulas in TÜ_projekt_protsess.pdf exactly. No invented constants.
"""

__version__ = "0.2.0"
