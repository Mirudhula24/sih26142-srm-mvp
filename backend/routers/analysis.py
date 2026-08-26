"""Inspection, report and assistant endpoints backed by completed SRM jobs."""
from datetime import datetime, timezone
from io import BytesIO
from typing import Optional

import rasterio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import LAND_COVER_CLASSES
from services import exporter, tasks

router = APIRouter()


class AssistantRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


def _completed(job_id: str):
    job = tasks.get_job_status(job_id)
    if job is None or job.status != "COMPLETED":
        raise HTTPException(404, "A completed mapping job is required.")
    return job


@router.get("/jobs/{job_id}/inspect")
def inspect_subpixel(job_id: str, lon: float, lat: float) -> dict:
    """Return the exact categorical value stored in the output COG at a map click."""
    _completed(job_id)
    path = exporter.cog_path_for_job(job_id)
    if path is None:
        raise HTTPException(404, "No raster available for this job.")
    with rasterio.open(path) as src:
        row, col = src.index(lon, lat)
        if not (0 <= row < src.height and 0 <= col < src.width):
            raise HTTPException(400, "Point lies outside the processed area.")
        value = int(src.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
    if value not in range(len(LAND_COVER_CLASSES)):
        raise HTTPException(404, "No valid land-cover class at this location.")
    return {
        "longitude": lon,
        "latitude": lat,
        "class_name": LAND_COVER_CLASSES[value],
        "class_fraction_percent": 100.0,
        "note": "Categorical output at this sub-pixel; fractional abundances are unavailable for this export.",
    }


@router.post("/jobs/{job_id}/assistant")
def spatial_assistant(job_id: str, request: AssistantRequest) -> dict:
    """Small, grounded natural-language interface over the completed job metrics."""
    job = _completed(job_id)
    question = request.question.lower()
    areas = job.class_area_sqm or {}
    percentages = job.class_distribution_percent or {}
    aliases = {
        "urban": "built_up", "built": "built_up", "building": "built_up",
        "forest": "vegetation", "tree": "vegetation", "green": "vegetation",
        "water": "water", "crop": "cropland", "farm": "cropland", "barren": "bare_soil", "bare": "bare_soil",
    }
    category: Optional[str] = next((value for key, value in aliases.items() if key in question), None)
    if any(word in question for word in ("change", "2024", "2026", "expansion", "deforestation", "loss")):
        answer = (
            "Temporal change needs two independently processed, date-specific calibrated maps. "
            "This job has one output only, so no expansion or loss figure is reported."
        )
    elif category:
        area_km2 = float(areas.get(category, 0)) / 1_000_000
        pct = float(percentages.get(category, 0))
        answer = f"{category.replace('_', ' ').title()} covers {area_km2:.2f} km² ({pct:.1f}%) in this processed AOI."
    else:
        summary = ", ".join(
            f"{name.replace('_', ' ')} {float(percentages.get(name, 0)):.1f}%"
            for name in LAND_COVER_CLASSES
        )
        answer = f"This mapping's land-cover distribution is: {summary}. Ask about urban area, vegetation, water, cropland, or barren land."
    return {"answer": answer, "grounded_job_id": job_id}


@router.get("/jobs/{job_id}/temporal-change")
def temporal_change(job_id: str) -> dict:
    _completed(job_id)
    return {
        "available": False,
        "message": "Run calibrated mappings for both 2024 and 2026 before computing change. Reference and baseline outputs cannot be used to claim temporal change.",
    }


@router.get("/jobs/{job_id}/executive-report.pdf")
def executive_report(job_id: str):
    """Generate a concise, branded PDF directly from the completed job metrics."""
    job = _completed(job_id)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise HTTPException(503, "PDF reporting is unavailable; install reportlab and restart the API.") from exc

    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    page_w, page_h = A4
    pdf.setFillColor(colors.HexColor("#0b1329"))
    pdf.rect(0, page_h - 42 * mm, page_w, 42 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(18 * mm, page_h - 20 * mm, "GeoSRM Executive Land-Cover Report")
    pdf.setFont("Helvetica", 9)
    pdf.drawString(18 * mm, page_h - 28 * mm, f"Job {job_id} | generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}")

    y = page_h - 56 * mm
    pdf.setFillColor(colors.HexColor("#0f172a"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(18 * mm, y, "Result summary")
    y -= 8 * mm
    pdf.setFont("Helvetica", 10)
    mode = (job.inference_mode or "unknown").replace("_", " ").title()
    pdf.drawString(18 * mm, y, f"Inference source: {mode}")
    y -= 6 * mm
    pdf.drawString(18 * mm, y, f"Output resolution: {10 / (job.scale_factor or 4):.1f} m")
    y -= 6 * mm
    pdf.drawString(18 * mm, y, "Accuracy note: mIoU is only shown when validated against labelled data.")
    y -= 12 * mm

    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(18 * mm, y, "Land-cover distribution")
    y -= 8 * mm
    pdf.setFillColor(colors.HexColor("#1e293b"))
    pdf.rect(18 * mm, y - 5 * mm, 174 * mm, 7 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(22 * mm, y - 1 * mm, "Class")
    pdf.drawRightString(138 * mm, y - 1 * mm, "Area (km²)")
    pdf.drawRightString(188 * mm, y - 1 * mm, "Coverage")
    y -= 8 * mm
    areas, pcts = job.class_area_sqm or {}, job.class_distribution_percent or {}
    pdf.setFont("Helvetica", 9)
    for index, name in enumerate(LAND_COVER_CLASSES):
        if index % 2 == 0:
            pdf.setFillColor(colors.HexColor("#f1f5f9"))
            pdf.rect(18 * mm, y - 5 * mm, 174 * mm, 7 * mm, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#0f172a"))
        pdf.drawString(22 * mm, y - 1 * mm, name.replace("_", " ").title())
        pdf.drawRightString(138 * mm, y - 1 * mm, f"{float(areas.get(name, 0)) / 1_000_000:.2f}")
        pdf.drawRightString(188 * mm, y - 1 * mm, f"{float(pcts.get(name, 0)):.1f}%")
        y -= 7 * mm
    y -= 7 * mm
    pdf.setFont("Helvetica-Oblique", 8)
    pdf.setFillColor(colors.HexColor("#475569"))
    pdf.drawString(18 * mm, y, "Use the GeoTIFF and GeoJSON exports for geospatial review. Do not interpret reference data as current change detection.")
    pdf.showPage()
    pdf.save()
    stream.seek(0)
    return StreamingResponse(stream, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{job_id}_executive_report.pdf"'
    })
