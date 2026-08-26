# Team role allocation

SIH caps participation at six members. Roles are split so the six workstreams stay
parallel — nobody blocks on anybody else's first commit.

| Role | Owns | Deliverables |
|---|---|---|
| Team lead & presenter | Architecture oversight, rubric tracking, pitch | Deck, live demo driving |
| Deep learning engineer | `ml_engine/` — D-SUN, SwinIR head, losses | Inference module, `sih26142_srm_v1.pth` |
| Geospatial data engineer | `backend/services/stac_fetcher.py`, `preprocessor.py` | STAC connectors, band alignment, cloud masking |
| Backend & spatial DB lead | `backend/routers/`, `database/`, TiTiler config | REST gateway, PostGIS container, COG export |
| Frontend web GIS developer | `frontend/` — dual canvas, slider, charts | React production build |
| UI/UX & QA lead | Styling, API tests, cache pre-loading, timing | Hardened compose setup, `data_cache/` assets |
