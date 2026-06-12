"""PDF report generator for HydroCalc (Phase 5).

Produces an A4 engineering-grade report from a completed AnalysisResult.
The report embeds the datasets.lock.json hash, formula revision, and
q_bar_k_source so a third party can replay any calculation byte-for-byte.

Usage
-----
    from backend.reporting.report import generate_pdf
    pdf_bytes = generate_pdf(result)          # result: AnalysisResult
"""

from __future__ import annotations

import io
import logging
import math
import os
from typing import Any

logger = logging.getLogger(__name__)

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import KeepTogether

from backend.models.schemas import AnalysisResult

# ---------------------------------------------------------------------------
# Register Bitstream Vera (bundled with ReportLab) — supports all Estonian
# characters (ä ö ü õ š ž) and common math symbols (Δ · −).
# ---------------------------------------------------------------------------
_RL_FONTS = os.path.join(os.path.dirname(reportlab.__file__), "fonts")

def _register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("Vera",   os.path.join(_RL_FONTS, "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("VeraBd", os.path.join(_RL_FONTS, "VeraBd.ttf")))
    pdfmetrics.registerFont(TTFont("VeraIt", os.path.join(_RL_FONTS, "VeraIt.ttf")))
    pdfmetrics.registerFont(TTFont("VeraBI", os.path.join(_RL_FONTS, "VeraBI.ttf")))
    pdfmetrics.registerFontFamily(
        "Vera",
        normal="Vera",
        bold="VeraBd",
        italic="VeraIt",
        boldItalic="VeraBI",
    )

_register_fonts()

FONT      = "Vera"
FONT_BOLD = "VeraBd"

# ---------------------------------------------------------------------------
# Text sanitizer — Vera (Bitstream Vera) covers Latin-1 + Latin Extended-A/B
# and most common punctuation but lacks combining diacritics (U+0300–U+036F),
# Greek letters, and subscript/superscript digits outside Latin-1.
# This helper swaps known problem sequences with ASCII-safe equivalents so
# every string passed to ReportLab renders cleanly.
# ---------------------------------------------------------------------------
_CHAR_MAP = {
    "Δ": "D",       # Δ Greek capital delta
    "δ": "d",       # δ Greek small delta
    "̄": "",        # combining macron — drop (q̄ becomes q)
    "₉": "9",       # subscript 9
    "₅": "5",       # subscript 5
    "ₛ": "s",       # subscript s
    "₀": "0",       # subscript 0
    "₂": "2",       # subscript 2
    "⚠": "(!)",     # ⚠ warning sign
    "—": "-",       # em dash
    "–": "-",       # en dash
    "−": "-",       # minus sign
}


def _safe(text: str) -> str:
    """Replace characters outside Vera's glyph set with ASCII equivalents."""
    for ch, replacement in _CHAR_MAP.items():
        text = text.replace(ch, replacement)
    return text

# ---------------------------------------------------------------------------
# Brand colours (Estonian blue palette)
# ---------------------------------------------------------------------------
BLUE_DARK = colors.HexColor("#1a3a5c")
BLUE_MID = colors.HexColor("#2a6099")
BLUE_LIGHT = colors.HexColor("#d6e8f7")
AMBER = colors.HexColor("#e8a000")
AMBER_LIGHT = colors.HexColor("#fff3cd")
RED = colors.HexColor("#c0392b")
RED_LIGHT = colors.HexColor("#fde8e6")
GRAY_BG = colors.HexColor("#f4f6f8")
GRAY_BORDER = colors.HexColor("#cdd4db")
WHITE = colors.white
BLACK = colors.black

W, H = A4  # 595.28 × 841.89 pt


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1",
            fontName="VeraBd",
            fontSize=16,
            leading=20,
            textColor=WHITE,
            spaceAfter=2 * mm,
        ),
        "h2": ParagraphStyle(
            "h2",
            fontName="VeraBd",
            fontSize=10,
            leading=13,
            textColor=BLUE_DARK,
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            fontName="Vera",
            fontSize=9,
            leading=12,
            textColor=BLUE_LIGHT,
        ),
        "body": ParagraphStyle(
            "body",
            fontName="Vera",
            fontSize=8,
            leading=11,
            textColor=BLACK,
        ),
        "body_small": ParagraphStyle(
            "body_small",
            fontName="Vera",
            fontSize=7,
            leading=10,
            textColor=colors.HexColor("#444444"),
        ),
        "warning": ParagraphStyle(
            "warning",
            fontName="VeraBd",
            fontSize=8,
            leading=11,
            textColor=RED,
        ),
        "result_label": ParagraphStyle(
            "result_label",
            fontName="Vera",
            fontSize=9,
            leading=12,
            textColor=BLUE_DARK,
        ),
        "result_value": ParagraphStyle(
            "result_value",
            fontName="VeraBd",
            fontSize=22,
            leading=26,
            textColor=BLUE_DARK,
        ),
        "result_unit": ParagraphStyle(
            "result_unit",
            fontName="Vera",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#555555"),
        ),
        "footer": ParagraphStyle(
            "footer",
            fontName="Vera",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#888888"),
        ),
    }


# ---------------------------------------------------------------------------
# Page template with header/footer callbacks
# ---------------------------------------------------------------------------

def _build_doc(buf: io.BytesIO, result: AnalysisResult) -> BaseDocTemplate:
    margin = 1.8 * cm

    def _header(canvas, doc):
        canvas.saveState()
        # Blue header bar
        canvas.setFillColor(BLUE_DARK)
        canvas.rect(0, H - 2.8 * cm, W, 2.8 * cm, fill=1, stroke=0)
        # Title
        canvas.setFillColor(WHITE)
        canvas.setFont("VeraBd", 14)
        canvas.drawString(margin, H - 1.6 * cm, "HÜDROLOOGILINE ARVUTUS")
        canvas.setFont("Vera", 8)
        canvas.setFillColor(BLUE_LIGHT)
        canvas.drawString(margin, H - 2.2 * cm,
                          "Karl Hommiku meetod · Maaparanduse eesvoolude dimensioneerimine")
        # Right: page number
        canvas.setFont("Vera", 7)
        canvas.drawRightString(W - margin, H - 2.2 * cm, f"lk {doc.page}")
        canvas.restoreState()

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(GRAY_BG)
        canvas.rect(0, 0, W, 1.0 * cm, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor("#888888"))
        canvas.setFont("Vera", 6.5)
        rid = result.run_id[:8]
        ts = result.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        rev = result.hommik.formula_revision
        canvas.drawString(margin, 0.35 * cm,
                          f"HydroCalc · run {rid} · {ts} · valem {rev}")
        canvas.drawRightString(W - margin, 0.35 * cm, "svam.ee")
        canvas.restoreState()

    frame = Frame(
        margin,
        1.2 * cm,  # bottom margin above footer
        W - 2 * margin,
        H - 2.8 * cm - 1.2 * cm,  # height between header and footer
        id="main",
    )
    template = PageTemplate(id="main", frames=[frame],
                            onPage=_header, onPageEnd=_footer)
    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        pageTemplates=[template],
        title=f"Hüdroloogiline arvutus — {result.river.name}",
        author="HydroCalc (svam.ee)",
        creator=f"HydroCalc · {result.hommik.formula_revision}",
    )
    return doc


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------

def _section(title: str, styles: dict) -> list:
    return [
        Spacer(1, 3 * mm),
        Paragraph(title, styles["h2"]),
        HRFlowable(width="100%", thickness=1, color=BLUE_MID, spaceAfter=2 * mm),
    ]


_TABLE_STYLE_BASE = TableStyle([
    ("FONT",      (0, 0), (-1, 0), "VeraBd", 7.5),
    ("FONT",      (0, 1), (-1, -1), "Vera", 7.5),
    ("BACKGROUND", (0, 0), (-1, 0), BLUE_DARK),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_BG]),
    ("GRID",      (0, 0), (-1, -1), 0.3, GRAY_BORDER),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
])


def _kv_table(rows: list[tuple[str, str]], col_widths: list[float]) -> Table:
    t = Table(rows, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONT",      (0, 0), (0, -1), "VeraBd", 7.5),
        ("FONT",      (1, 0), (1, -1), "Vera", 7.5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, GRAY_BG]),
        ("GRID",      (0, 0), (-1, -1), 0.3, GRAY_BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN",    (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _meta_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    ts = result.timestamp.strftime("%d.%m.%Y %H:%M UTC")
    p = result.hommik  # HommikResult for p_percent — not stored separately :(
    # p_percent comes from the request, which isn't stored in AnalysisResult.
    # We can back-derive it from q_veg_max if needed, but it's cleaner to just
    # show the computed values without repeating p.  The warnings list contains
    # the placeholder notices.
    rows = [
        ("Arvutuse kuupäev", ts),
        ("Arvutuse ID", result.run_id),
        ("Valem", result.hommik.formula_revision),
        ("q_bar_k allikas", _safe("kartogramm" if result.hommik.q_bar_k_source == "raster" else "asendusarvutus (7.0 l/(s·km²))")),
    ]
    col_w = [usable_w * 0.35, usable_w * 0.65]
    return _section("Arvutuse andmed", styles) + [_kv_table(rows, col_w)]


def _input_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    pt = result.input_point_lest97
    snapped = result.snapped_point_lest97
    r = result.river
    c = result.catchment
    rows = [
        ("Sisestuspunkt (L-EST97)", f"X = {pt.x:.1f} m, Y = {pt.y:.1f} m"),
        ("Lähimale jõele klammerdus", f"X = {snapped.x:.1f} m, Y = {snapped.y:.1f} m  (kaugus {result.snap_distance_m:.0f} m)"),
        ("Vooluveekogu nimi", r.name),
        ("Vooluveekogu kood", r.code),
        ("Vooluveekogu tüüp", r.river_type or "—"),
        ("Peajõgi / lisajõgi", "peajõgi" if r.is_main else "lisajõgi / kraav"),
        ("Valgala nimi", c.name or "—"),
        ("Valgala kood", c.code or "—"),
        ("Valgala pindala A", f"{c.area_km2:.4f} km²"),
    ]
    if result.hommik.area_floored_to_100km2:
        rows.append(("Arvutuses kasutatud A", "100.0000 km²  (väiksemad valglad piiratakse 100 km²-ga)"))
    col_w = [usable_w * 0.38, usable_w * 0.62]
    return _section("Sisendandmed", styles) + [_kv_table(rows, col_w)]


def _landcover_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    lc = result.landcover
    header = ["Sümbol", "Kirjeldus", "Väärtus (%)"]
    data = [header] + [
        ["A_ms", "Madalsood ja soometsad",    f"{lc.A_ms:.2f}"],
        ["A_r",  "Rabad",                      f"{lc.A_r:.2f}"],
        ["A_km", "Intensiivselt kuivendatud madalsood", f"{lc.A_km:.2f}"],
        ["B",    "Mets ja võsa mineraalmaal",  f"{lc.B:.2f}"],
        ["C",    "Lage mineraalmaa",           f"{lc.C:.2f}"],
        ["maaparandus", "Maaparandusmõjuala", f"{lc.maaparandus:.2f}"],
        ["a",    "Dq parameeter (märg mineraal + A_km)", f"{lc.a_wet_mineral_plus_akm:.2f}"],
    ]
    col_w = [usable_w * 0.12, usable_w * 0.62, usable_w * 0.26]
    t = Table(data, colWidths=col_w)
    t.setStyle(_TABLE_STYLE_BASE)
    return _section("Maakasutus (ETAK kõlvikud)", styles) + [t]


def _calc_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    h = result.hommik
    lc = result.landcover
    q95_note = "(asendusarvutus)" if h.q_bar_k_source == "placeholder" else "(kartogramm)"
    header = ["Valem", "Parameeter", "Väärtus", "Ühik"]
    data = [header] + [
        ["(1.1)", "q_bar_k  (klimaatiline norm) " + q95_note,
         f"{h.q_bar_l_per_s_km2 - h.delta_q_l_per_s_km2:.4f}", "l/(s·km²)"],
        ["(1.2)", "Dq = 0,020·a + 0,30·q95% − 1,00",
         f"{h.delta_q_l_per_s_km2:.4f}", "l/(s·km²)"],
        ["(1.1)", "q_bar = q_bar_k + Dq",
         f"{h.q_bar_l_per_s_km2:.4f}", "l/(s·km²)"],
        ["(1.4)", "k95% = q95% / q_bar",
         f"{h.k95:.4f}", "—"],
        ["(1.5)", "r_s  (sügisene äravooluparameeter)",
         f"{h.r_s:.4f}", "—"],
        ["(1.7)", "r   (kevadine äravooluparameeter)",
         f"{h.r:.4f}", "—"],
        ["(1.3)", "q_veg.max  (sügisene tippäravoolu moodul)",
         f"{h.q_veg_max_l_per_s_km2:.4f}", "l/(s·km²)"],
        ["(1.6)", "q_kev.maks  (kevadine tippäravoolu moodul)",
         f"{h.q_kev_max_l_per_s_km2:.4f}", "l/(s·km²)"],
        ["(1.8)", "Q_veg = q_veg \xb7 A / 1000",
         f"{h.Q_veg_max_m3_per_s:.4f}", "m³/s"],
        ["(1.8)", "Q_kev = q_kev \xb7 A / 1000",
         f"{h.Q_kev_max_m3_per_s:.4f}", "m³/s"],
    ]
    col_w = [usable_w * 0.10, usable_w * 0.50, usable_w * 0.20, usable_w * 0.20]
    t = Table(data, colWidths=col_w)
    t.setStyle(_TABLE_STYLE_BASE)
    # Highlight the final Q rows
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 9), (-1, 9), BLUE_LIGHT),
        ("BACKGROUND", (0, 10), (-1, 10), BLUE_LIGHT),
        ("FONT", (0, 9), (-1, 10), "VeraBd", 7.5),
    ]))
    return _section("Arvutuskäik", styles) + [t]


def _results_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    h = result.hommik
    inner_w = (usable_w - 4 * mm) / 2

    def _result_cell(label: str, value: float, color: str) -> Table:
        c = colors.HexColor(color)
        rows = [
            [Paragraph(label, styles["result_label"])],
            [Paragraph(f"{value:.3f}", ParagraphStyle(
                "rv", fontName="VeraBd", fontSize=26, leading=30, textColor=c))],
            [Paragraph("m³/s", styles["result_unit"])],
        ]
        t = Table(rows, colWidths=[inner_w])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), GRAY_BG),
            ("BOX", (0, 0), (0, -1), 1.5, c),
            ("TOPPADDING", (0, 0), (0, -1), 4),
            ("BOTTOMPADDING", (0, 0), (0, -1), 4),
            ("LEFTPADDING", (0, 0), (0, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ]))
        return t

    kev = _result_cell("Q_kev.maks (kevadine tippvooluhulk)", h.Q_kev_max_m3_per_s, "#1a3a5c")
    veg = _result_cell("Q_veg.maks (sügisene tippvooluhulk)", h.Q_veg_max_m3_per_s, "#1a6060")

    pair = Table([[kev, veg]], colWidths=[inner_w + 2 * mm, inner_w + 2 * mm])
    pair.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))
    return _section("Tulemused", styles) + [pair]


def _warnings_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    if not result.warnings:
        return []
    items = []
    for w in result.warnings:
        is_placeholder = "placeholder" in w or "asendusarvutus" in w
        bg = AMBER_LIGHT if is_placeholder else RED_LIGHT
        fg = colors.HexColor("#7a5000") if is_placeholder else RED
        p = Paragraph(_safe(f"(!) {w}"), ParagraphStyle(
            "wi", fontName="Vera", fontSize=7.5, leading=11, textColor=fg))
        t = Table([[p]], colWidths=[usable_w])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.5,
             AMBER if is_placeholder else RED),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        items.append(Spacer(1, 1.5 * mm))
        items.append(t)
    return _section("Hoiatused", styles) + items


def _datasets_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    if not result.dataset_versions:
        return []
    header = ["Andmestik", "Laaditud", "SHA-256 (algus)"]
    data = [header] + [
        [d.name,
         d.retrieved_at.strftime("%Y-%m-%d"),
         d.sha256[:16] + "…"]
        for d in result.dataset_versions
    ]
    col_w = [usable_w * 0.35, usable_w * 0.20, usable_w * 0.45]
    t = Table(data, colWidths=col_w)
    t.setStyle(_TABLE_STYLE_BASE)
    note = Paragraph(
        "Täielikud SHA-256 räsid on salvestatud datasets.lock.json faili. "
        "Need võimaldavad arvutust aastaid hiljem byte-täpsusega korrata.",
        styles["body_small"],
    )
    return _section("Andmeallikad (reprodutseeritavus)", styles) + [t, Spacer(1, 2 * mm), note]


# ---------------------------------------------------------------------------
# Catchment map image (Pillow — no extra deps beyond what's in requirements)
# ---------------------------------------------------------------------------

_MAAMET_WMS = "https://kaart.maaamet.ee/wms/alus"
_WMS_LAYER  = "pohi_vr2"   # Maa-amet topographic base map in EPSG:3301


def _fetch_wms_background(
    minx: float, miny: float, maxx: float, maxy: float,
    width: int, height: int,
) -> "PIL.Image.Image | None":
    """Fetch a Maa-amet kaart tile via WMS (EPSG:3301 bbox).

    Returns a PIL Image on success, None if the request fails (offline /
    server error) so the caller can fall back to a plain background.
    """
    try:
        import httpx
        from PIL import Image as PILImage

        params = {
            "SERVICE": "WMS", "VERSION": "1.1.1", "REQUEST": "GetMap",
            "LAYERS": _WMS_LAYER, "STYLES": "",
            "BBOX": f"{minx},{miny},{maxx},{maxy}",
            "WIDTH": str(width), "HEIGHT": str(height),
            "SRS": "EPSG:3301",
            "FORMAT": "image/png", "TRANSPARENT": "false",
        }
        resp = httpx.get(_MAAMET_WMS, params=params, timeout=8.0)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image/"):
            return PILImage.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as exc:
        logger.info("WMS background fetch failed (will use plain background): %s", exc)
    return None


def _render_catchment_png(result: AnalysisResult) -> bytes | None:
    """Render the catchment polygon + pour point as a PNG.

    Uses Maa-amet kaart WMS as the background (EPSG:3301).  Falls back to a
    plain light-blue background if the WMS call fails (e.g. offline).
    The catchment GeoJSON is in WGS84 — converted to L-EST97 for pixel math.

    Returns raw PNG bytes, or None if anything fails (image is optional).
    """
    if result.catchment_geojson is None:
        return None
    try:
        from PIL import Image, ImageDraw
        from shapely.geometry import shape as shapely_shape
        from shapely.ops import transform as shapely_transform

        from backend.gis.crs import _transformer, LEST97, WGS84

        # Re-project catchment from WGS84 → L-EST97 for EPSG:3301 pixel math
        geom_wgs84 = shapely_shape(result.catchment_geojson)
        t = _transformer(WGS84, LEST97)
        geom = shapely_transform(t.transform, geom_wgs84)

        minx, miny, maxx, maxy = geom.bounds

        # 15 % margin
        dx = max((maxx - minx) * 0.15, 100.0)
        dy = max((maxy - miny) * 0.15, 100.0)
        minx -= dx; maxx += dx
        miny -= dy; maxy += dy

        # Canvas dimensions — preserve real-world aspect ratio (L-EST97 is metric)
        extent_x = maxx - minx
        extent_y = maxy - miny
        MAX_DIM = 440
        if extent_x >= extent_y:
            img_w = MAX_DIM
            img_h = max(80, int(extent_y / extent_x * MAX_DIM))
        else:
            img_h = MAX_DIM
            img_w = max(80, int(extent_x / extent_y * MAX_DIM))

        def to_px(x: float, y: float) -> tuple[int, int]:
            px = int((x - minx) / (maxx - minx) * img_w)
            py = int((maxy - y) / (maxy - miny) * img_h)
            return px, py

        # --- Background: try WMS, fall back to plain colour ---
        bg = _fetch_wms_background(minx, miny, maxx, maxy, img_w, img_h)
        if bg is not None:
            img = bg.resize((img_w, img_h))
        else:
            img = Image.new("RGB", (img_w, img_h), (240, 245, 250))

        draw = ImageDraw.Draw(img, "RGBA")

        # --- Catchment polygon (semi-transparent blue fill) ---
        def _draw_poly(poly) -> None:
            pts = [to_px(x, y) for x, y in poly.exterior.coords]
            draw.polygon(pts, fill=(25, 100, 200, 80), outline=(25, 75, 155, 255))
            for interior in poly.interiors:
                ipts = [to_px(x, y) for x, y in interior.coords]
                draw.polygon(ipts, fill=(240, 245, 250, 200), outline=(25, 75, 155, 200))

        if geom.geom_type == "MultiPolygon":
            for part in geom.geoms:
                _draw_poly(part)
        else:
            _draw_poly(geom)

        # --- Pour point marker (red) — snapped stream point ---
        px, py = to_px(result.snapped_point_lest97.x, result.snapped_point_lest97.y)
        r = 6
        draw.ellipse([(px - r, py - r), (px + r, py + r)],
                     fill=(220, 30, 30, 230), outline=(100, 0, 0, 255))

        # --- Clicked point marker (blue) — original user input ---
        cx, cy = to_px(result.input_point_lest97.x, result.input_point_lest97.y)
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)],
                     fill=(37, 99, 235, 210), outline=(29, 78, 216, 255))

        # --- North arrow ---
        draw.text((img_w - 22, 6), "N", fill=(30, 30, 30, 220))
        draw.line([(img_w - 16, 18), (img_w - 16, 8)], fill=(30, 30, 30, 220), width=1)
        draw.polygon([(img_w - 19, 14), (img_w - 13, 14), (img_w - 16, 8)],
                     fill=(30, 30, 30, 220))

        # --- Border ---
        draw.rectangle([(0, 0), (img_w - 1, img_h - 1)], outline=(160, 180, 200, 255))

        # Flatten RGBA → RGB before saving as PNG for ReportLab
        flat = Image.new("RGB", (img_w, img_h), (255, 255, 255))
        flat.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)

        buf = io.BytesIO()
        flat.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as exc:  # image is optional — never crash the PDF
        logger.warning("catchment map PNG failed: %s", exc)
        return None


def _map_section(result: AnalysisResult, styles: dict, usable_w: float) -> list:
    """Return a PDF section with the catchment map image, or [] if unavailable."""
    from PIL import Image as PILImage
    from reportlab.platypus import Image as RLImage

    png = _render_catchment_png(result)
    if png is None:
        return []

    pil = PILImage.open(io.BytesIO(png))
    aspect = pil.height / pil.width
    rl_w = usable_w * 0.75          # use 75 % of page width — readable but not oversized
    rl_h = rl_w * aspect

    rl_img = RLImage(io.BytesIO(png), width=rl_w, height=rl_h)
    caption = Paragraph(
        _safe(
            "Joonis 1. Valgala piir (sinine), jõele klammerduspunkt (punane) ja sisestuspunkt (sinine). "
            "Taustakaart: Maa-amet aluskaart (EPSG:3301). "
            "Allikas: kaart.maaamet.ee."
        ),
        styles["body_small"],
    )
    return _section("Asukohakaart", styles) + [rl_img, Spacer(1, 2 * mm), caption]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_pdf(result: AnalysisResult) -> bytes:
    """Generate an A4 PDF report from a completed AnalysisResult.

    Returns raw PDF bytes suitable for a ``StreamingResponse``.
    """
    buf = io.BytesIO()
    doc = _build_doc(buf, result)
    styles = _make_styles()
    margin = 1.8 * cm
    usable_w = W - 2 * margin

    story: list[Any] = []
    story += _meta_section(result, styles, usable_w)
    story += _map_section(result, styles, usable_w)
    story += _input_section(result, styles, usable_w)
    story += _landcover_section(result, styles, usable_w)
    story += _calc_section(result, styles, usable_w)
    story += [KeepTogether(_results_section(result, styles, usable_w))]
    story += _warnings_section(result, styles, usable_w)
    story += _datasets_section(result, styles, usable_w)

    doc.build(story)
    return buf.getvalue()
