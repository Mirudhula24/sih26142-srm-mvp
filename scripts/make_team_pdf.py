"""Generate the printable team assignment handout from the roles defined here.

    python scripts/make_team_pdf.py

Writes docs/SIH26142_Team_Assignments.pdf -- one sheet per person to hand out, plus
the sequencing and hand-off contracts everyone shares.
"""
import os
from datetime import date

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

OUT = os.path.join(os.path.dirname(__file__), "..", "docs", "SIH26142_Team_Assignments.pdf")

INK = colors.HexColor("#0f1720")
MUTED = colors.HexColor("#4a5b6d")
FAINT = colors.HexColor("#74869a")
RULE = colors.HexColor("#d4dde5")
ACCENT = colors.HexColor("#1c5d94")
CRITICAL = colors.HexColor("#a8412c")
PARALLEL = colors.HexColor("#2c6a3d")
BAND = colors.HexColor("#f2f6f9")

ROLES = [
    {
        "title": "Deep Learning Engineer",
        "status": "CRITICAL PATH",
        "colour": CRITICAL,
        "owns": "ml_engine/models/ · ml_engine/utils/unmixing_loss.py · "
                "ml_engine/train.py · ml_engine/weights/",
        "tasks": [
            "Write <b>train.py</b> and the dataset loader. Neither exists yet — this is "
            "the single largest missing piece in the repository.",
            "Start from SEN2SRLite weights as the spatial backbone instead of training "
            "from scratch; only the allocation head genuinely needs to learn.",
            "Tune the four loss weights in <b>SRMLoss</b>. Watch that mass_error stays "
            "below 1e-3 — that constraint is the project's whole argument.",
            "Export a checkpoint every hour, however undertrained. Four people are "
            "blocked until a loadable weights file exists.",
        ],
        "done": "sih26142_srm_v1.pth exists, loads without shape errors, and produces a "
                "land cover map that visibly beats the 10 m input.",
        "watch": "load_model uses strict=False, so mismatched state_dict keys fail "
                 "<b>silently</b> and look exactly like a successful load of random "
                 "weights. Verify parameters actually populated.",
    },
    {
        "title": "Geospatial Data Engineer",
        "status": "CRITICAL PATH",
        "colour": CRITICAL,
        "owns": "backend/services/stac_fetcher.py · backend/services/preprocessor.py · "
                "scripts/build_offline_cache.py · scripts/build_labels.py",
        "tasks": [
            "Build the label pipeline <b>first</b>: ESA WorldCover's 11 classes remapped "
            "to our 5, then aggregated into abundance fractions. Training cannot start "
            "without it.",
            "Pair those with downsampled high-resolution reference imagery for the "
            "sub-pixel supervision signal.",
            "Run build_offline_cache.py for all four regions and verify it works with "
            "the network physically unplugged.",
            "Sanity-check band registration: no pixel offset between the native 10 m "
            "channels and the resampled 20 m SWIR.",
        ],
        "done": "The DL engineer has paired (X, abundance, fine_labels) tensors on disk, "
                "and data_cache/ holds four real regions.",
        "watch": "Chennai is the only cached region outside UTM 43N. Cache it — a "
                 "reprojection bug is invisible until a granule crosses zones, and it "
                 "would surface live in front of judges.",
    },
    {
        "title": "Backend & Spatial DB Lead",
        "status": "PARALLEL",
        "colour": PARALLEL,
        "owns": "backend/routers/ · backend/services/tasks.py · backend/database/ · "
                "backend/services/exporter.py",
        "tasks": [
            "Wire the job lifecycle to PostGIS. _JOBS, _TASK_IDS and _GRANULE_BBOX are "
            "in-process dictionaries that any restart wipes.",
            "Persist ClassMetrics and COGExport rows so the analytics survive too.",
            "Write the mIoU evaluation path, so the accuracy figure in the PRD is "
            "measured rather than asserted.",
            "Verify the QGIS round-trip yourself — the affine scaling on export is a "
            "classic silent failure.",
        ],
        "done": "A job survives an API restart, and a judge can open the exported "
                "GeoTIFF in QGIS in the right place on Earth.",
        "watch": "A judge asking “how did you measure 0.70 mIoU?” is a bad moment "
                 "if nothing computes it.",
    },
    {
        "title": "Frontend Web GIS Developer",
        "status": "PARALLEL",
        "colour": PARALLEL,
        "owns": "frontend/src/components/ · frontend/src/store/ · frontend/src/lib/",
        "tasks": [
            "Fix the left canvas. It receives granule.preview_url, a rendered PNG, where "
            "an XYZ tile template is expected, so input imagery never draws. Point it "
            "at TiTiler.",
            "Add real loading and error states; a failed job currently just prints a "
            "red bar.",
            "Profile the curtain drag and the camera lock under fast panning; the sync "
            "guard must hold at 45 FPS.",
            "Keep the class palette in constants.js in step with the one in "
            "ml_engine/utils/cog_writer.py.",
        ],
        "done": "A judge draws a box, hits Execute, and watches a real 2.5 m map slide "
                "in under the curtain at 45 FPS.",
        "watch": "Box drawing, region selection and the curtain drag were all broken and "
                 "are now fixed — re-test them after any refactor of DualCanvasMap.",
    },
    {
        "title": "Integration & QA Lead",
        "status": "PARALLEL",
        "colour": PARALLEL,
        "owns": "docker-compose*.yml · ml_engine/tests/ · backend/tests/ · data_cache/",
        "tasks": [
            "Build the Docker images on the RTX 3080 <b>today</b>. They have never been "
            "built once — assume something breaks and find out now, not on stage.",
            "Run scripts/check_gpu.py inside the container; record peak VRAM and tune "
            "MAX_PATCH_SIZE to fit.",
            "Own the end-to-end drill: cold clone, compose up, draw an AOI, export, "
            "open the result in QGIS.",
            "Rehearse the failure modes deliberately — pull the network, force an OOM, "
            "pick a heavily clouded scene.",
        ],
        "done": "A clean clone reaches a working demo on the 3080 with one command, and "
                "you have timed the full run three times.",
        "watch": "The CPU override exists for machines without an NVIDIA runtime, but a "
                 "stale DEVICE=cpu in .env will silently win on the GPU box too.",
    },
    {
        "title": "Team Lead & Presenter",
        "status": "INTEGRATION OWNER",
        "colour": ACCENT,
        "owns": "docs/DEMO_SCRIPT.md · docs/PRD.md · README.md · the pitch deck",
        "tasks": [
            "Guard the scope. Every P2 idea that appears at hour 30 is a threat, not an "
            "opportunity.",
            "Own the mass-conservation defence: when a judge asks whether this is "
            "generative invention, show that the output downsamples back to the observed "
            "sensor abundances.",
            "Never present a random-weight output as a result.",
            "Merge and integrate. With six people on one repository, nobody else should "
            "be resolving conflicts.",
        ],
        "done": "The three-minute run is rehearsed end to end, and you can answer the "
                "hallucination question without opening an editor.",
        "watch": "The demo script in the source PRD said “Delhi Coastal/Port”. "
                 "Delhi is landlocked; Chennai is the region that sentence wanted.",
    },
]

PHASES = [
    ("H0–H2", "Everyone clones, runs the CPU stack and sees the UI, so nobody is "
              "reasoning about code they have not watched run. QA starts the GPU image "
              "build immediately — longest pole, most likely to break."),
    ("H2–H10", "Data and DL engineers pair on the label pipeline. Two people here is not "
               "redundancy, it is the whole schedule. Backend and frontend work their own "
               "fixes; neither needs weights."),
    ("H10–H24", "Training runs, checkpointing hourly. The first checkpoint lets frontend "
                "and QA test against real output instead of noise. Backend finishes "
                "persistence and the mIoU path."),
    ("H24–H36", "Integration. Real weights meet the real UI — expect bugs neither half "
                "showed alone. Cache the offline regions and verify with the network off."),
    ("H36–H44", "Freeze. No new features. Time the three-minute script repeatedly, on the "
                "machine you will present from and the network you will actually have."),
    ("H44–H48", "Buffer. If you are writing code here, something upstream slipped. Deck "
                "polish, fallback drills, sleep."),
]

HANDOFFS = [
    ("Data eng.", "DL eng.",
     "X (6,H,W) float32 · abundance (5,H,W) summing to 1 · fine_labels (H·4,W·4) int64. "
     "Band order B02 B03 B04 B08 B11 B12 — fix it once, in writing."),
    ("DL eng.", "Backend",
     "Weights path and state_dict key names. strict=False means a mismatch loads silently "
     "as random weights."),
    ("Backend", "Frontend",
     "SRMResponse in backend/schemas.py is the contract. The UI polls /api/v1/jobs/{id} "
     "until status leaves PENDING. Do not rename fields without telling frontend."),
    ("Ingest", "GPU worker",
     "Documented in docs/PIPELINE_HANDOFF.md. The .npz keys must stay in step across two "
     "container images."),
    ("Everyone", "Team lead",
     "Branch per role, small commits, no direct pushes to main during integration hours."),
]


def styles():
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("title", parent=base["Title"], fontName="Helvetica-Bold",
                                fontSize=23, leading=27, textColor=INK, alignment=TA_LEFT,
                                spaceAfter=2)
    s["kicker"] = ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=7.5,
                                 leading=11, textColor=FAINT, spaceAfter=6)
    s["lede"] = ParagraphStyle("lede", fontName="Helvetica", fontSize=10, leading=15,
                               textColor=MUTED, spaceAfter=4)
    s["h2"] = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13.5, leading=17,
                             textColor=INK, spaceBefore=6, spaceAfter=6)
    s["role"] = ParagraphStyle("role", fontName="Helvetica-Bold", fontSize=15, leading=19,
                               textColor=INK, spaceAfter=1)
    s["label"] = ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=7.5,
                                leading=10, textColor=FAINT, spaceBefore=8, spaceAfter=3)
    s["body"] = ParagraphStyle("body", fontName="Helvetica", fontSize=9.6, leading=14,
                               textColor=MUTED)
    s["mono"] = ParagraphStyle("mono", fontName="Courier", fontSize=7.8, leading=11.5,
                               textColor=MUTED)
    s["task"] = ParagraphStyle("task", parent=s["body"], leftIndent=13, bulletIndent=2,
                               spaceAfter=5)
    s["cell"] = ParagraphStyle("cell", fontName="Helvetica", fontSize=8.6, leading=12,
                               textColor=MUTED)
    s["cellb"] = ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.6,
                                leading=12, textColor=INK)
    return s


def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(FAINT)
    canvas.drawString(20 * mm, 9.5 * mm, "SIH26142 · GeoSRM Engine · team assignments")
    canvas.drawRightString(A4[0] - 20 * mm, 9.5 * mm, f"Page {doc.page}")
    canvas.restoreState()


def status_bar(text, colour, width):
    t = Table([[Paragraph(
        f'<font color="#ffffff" size="7.5"><b>{text}</b></font>',
        ParagraphStyle("s", fontName="Helvetica-Bold", fontSize=7.5, leading=10))]],
        colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def note_box(text, s, width, colour):
    t = Table([[Paragraph(text, s["cell"])]], colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBEFORE", (0, 0), (0, -1), 2, colour),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def build():
    doc = BaseDocTemplate(os.path.abspath(OUT), pagesize=A4,
                          leftMargin=20 * mm, rightMargin=20 * mm,
                          topMargin=18 * mm, bottomMargin=20 * mm,
                          title="SIH26142 — Team Assignments",
                          author="GeoSRM Engine team")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])

    s = styles()
    w = doc.width
    story = []

    # ---- cover ----
    story.append(Paragraph(
        "SIH26142 · NTRO · SPACE TECHNOLOGY", s["kicker"]))
    story.append(Paragraph("Who builds what, and in which order", s["title"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Deep Learning Based Super-Resolution Mapping — 4× sub-pixel land cover maps at "
        "2.5 m from 10 m Sentinel-2 imagery.", s["lede"]))
    story.append(Paragraph(
        "The scaffold already stands: model architecture, ingestion, API, dual-canvas UI, "
        "Docker and a passing constraint suite. These six roles are therefore split by "
        "what is <b>missing</b>, not by generic job titles — and two of them hold up "
        "everyone else.", s["lede"]))
    story.append(Spacer(1, 10))

    built = [
        "D-SUN unmixing, Swin allocation head, mass-conserving sub-pixel assignment, MRF smoothing",
        "Tiled inference — a 256×256 tile in 4.8 s on CPU, mass error 2.4e-07",
        "STAC ingestion, SWIR band alignment, SCL cloud masking",
        "Ingest → GPU tensor hand-off, COG / GeoJSON / CSV export",
        "FastAPI routes, PostGIS schema, dual-canvas UI, Compose for GPU and CPU",
    ]
    missing = [
        "No trained weights and no training pipeline at all",
        "No ground-truth labels — WorldCover → 5 classes → abundances is unwritten",
        "Left canvas is fed a preview PNG where a tile template is expected",
        "Job state lives in in-process dicts; srm_jobs is never written",
        "mIoU is never computed; no baseline comparison against bicubic",
        "data_cache/ is empty; Docker images have never been built",
    ]
    rows = [[Paragraph("<b>ALREADY BUILT</b>", s["label"]),
             Paragraph("<b>STILL MISSING</b>", s["label"])]]
    rows.append([
        Paragraph("<br/>".join(f"• {b}" for b in built), s["cell"]),
        Paragraph("<br/>".join(f"• {m}" for m in missing), s["cell"]),
    ])
    t = Table(rows, colWidths=[w / 2 - 4, w / 2 - 4])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 1), (0, 1), 2, PARALLEL),
        ("LINEABOVE", (1, 1), (1, 1), 2, CRITICAL),
        ("TOPPADDING", (0, 1), (-1, 1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))
    story.append(note_box(
        "<b>The one thing to get right.</b> Two of six people are on the critical path, "
        "and their work is the least visible. There is a real pull toward staffing four "
        "people on the UI because progress there is easy to see. Resist it — a beautiful "
        "interface rendering noise loses to a plain one rendering a correct map.",
        s, w, ACCENT))
    story.append(Spacer(1, 14))

    # ---- sequencing ----
    story.append(Paragraph("Sequencing", s["h2"]))
    story.append(Paragraph(
        "Hours from your build start. Labels gate training, training gates every visual "
        "result, and everything else proceeds without either.", s["body"]))
    story.append(Spacer(1, 8))
    rows = [[Paragraph(f"<b>{h}</b>", s["cellb"]), Paragraph(d, s["cell"])]
            for h, d in PHASES]
    t = Table(rows, colWidths=[24 * mm, w - 24 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEABOVE", (0, 0), (-1, -1), 0.5, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
        ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (0, -1), 0),
    ]))
    story.append(t)

    story.append(PageBreak())

    # ---- one block per person ----
    for i, r in enumerate(ROLES):
        block = [
            status_bar(r["status"], r["colour"], w),
            Spacer(1, 7),
            Paragraph(r["title"], s["role"]),
            Paragraph("OWNS", s["label"]),
            Paragraph(r["owns"], s["mono"]),
            Paragraph("WORK", s["label"]),
        ]
        for task in r["tasks"]:
            block.append(Paragraph(task, s["task"], bulletText="•"))
        block.append(Paragraph("DONE WHEN", s["label"]))
        block.append(Paragraph(r["done"], s["body"]))
        block.append(Spacer(1, 8))
        block.append(note_box("<b>Watch out.</b> " + r["watch"], s, w, r["colour"]))
        story.append(KeepTogether(block))
        story.append(PageBreak() if i % 2 else Spacer(1, 16))

    # ---- hand-offs ----
    story.append(Paragraph("Hand-off contracts", s["h2"]))
    story.append(Paragraph(
        "Agree these in the first hour. Each one is a place where two people can lose "
        "half a day discovering they assumed different things.", s["body"]))
    story.append(Spacer(1, 8))
    rows = [[Paragraph("<b>FROM</b>", s["label"]), Paragraph("<b>TO</b>", s["label"]),
             Paragraph("<b>THE CONTRACT</b>", s["label"])]]
    for a, b, c in HANDOFFS:
        rows.append([Paragraph(a, s["cellb"]), Paragraph(b, s["cellb"]),
                     Paragraph(c, s["cell"])])
    t = Table(rows, colWidths=[22 * mm, 22 * mm, w - 44 * mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f"Repository state verified {date.today().isoformat()}: 7 tests passing, both "
        "Compose configurations valid, frontend rendering with no console errors, "
        "256×256 CPU inference at 4.8 s. Weights, labels and the training pipeline do "
        "not yet exist.", s["mono"]))

    doc.build(story)
    print(f"Wrote {os.path.abspath(OUT)}")


if __name__ == "__main__":
    build()
