"""POST /api/report — generate a PDF report from an AnalysisResult.

The client re-submits the full AnalysisResult JSON it received from
POST /api/analyze.  The server regenerates the PDF deterministically
from those values and streams it back.  No server-side state is required.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from backend.models.schemas import AnalysisResult
from backend.reporting.report import generate_pdf

router = APIRouter(prefix="/api", tags=["report"])


@router.post("/report")
async def report(result: AnalysisResult) -> StreamingResponse:
    """Generate and stream a PDF report for a completed analysis.

    The client POSTs the ``AnalysisResult`` JSON it received from
    ``/api/analyze``.  Returns ``application/pdf``.
    """
    pdf_bytes = generate_pdf(result)
    filename = f"hydrocalc_{result.run_id[:8]}_{result.river.name.replace(' ', '_')}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
