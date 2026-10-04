# CrisisOps — Disaster Response Memory Engine

[![Live Demo](https://img.shields.io/badge/Live%20Demo-crisisops--9541.onrender.com-111827?style=flat-square)](https://crisisops-9541.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-111827?style=flat-square)](LICENSE)

[Architecture overview](docs/ARCHITECTURE.md) · [Portfolio](https://sanjeevakumarnani.github.io)

CrisisOps is a persistent operational memory for emergency response. It turns field reports into a common operational picture, retains what happened, recalls relevant history before a response plan is chosen, and reflects on recurring patterns and constraints.

## Core loop
Capture → Retain → Recall → Reflect → Human decision → Outcome → Future memory.

## What it covers
- affected locations and people
- urgent needs and their status
- available and committed resources
- responder presence and ETA
- transportation constraints
- local operational conditions
- attempted actions and outcomes
- source and timestamp provenance
- memory-backed response-plan review
- before/after demonstration of memory impact
- synthetic demo dataset and CSV import
- FastAPI API, SQLite persistence, Docker and Render deployment configuration

## Hindsight
The memory bank is `crisisops-disaster-response-memory`. Configure `HINDSIGHT_BASE_URL` and `HINDSIGHT_API_KEY` for live Hindsight. Without credentials, the UI runs in clearly labelled demo mode with local similarity fallback.

## Run locally
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://localhost:8000` and select **Load response exercise**.

## Deployment
Render can use the included `render.yaml`. Add the Hindsight environment variables as secrets.

## Safety
CrisisOps is decision support, not an autonomous dispatch system. It does not send responders, alter routes, or assert unverified live facts.


## Live public data

The dashboard now separates **live external intelligence** from **human field reports**:

- **Open-Meteo**: current weather and short-horizon precipitation/wind conditions for the selected location.
- **India Meteorological Department (IMD) CAP feed**: current public warning messages published through the IMD CAP source.
- **USGS Earthquake Hazards Program**: past-day earthquake feed, filtered to a configurable radius around the selected location.
- **GDACS**: global disaster events when the public API returns them.

The default view is Hyderabad (17.3850, 78.4867), but the API accepts latitude/longitude so the same engine can be used for another operating area.

Public feeds are never represented as verified field status. Each live signal retains its source and timestamp, while human-entered reports remain the operational ground-truth layer.

### Memory learning with real signals

Use **Retain in Hindsight** after refreshing the live intelligence panel. CrisisOps then stores the current public signals in the Hindsight memory bank with stable document IDs, source tags and timestamps. A later plan review can recall those signals alongside retained field reports.

This makes the learning loop demonstrable:

**Live signal → Retain → Recall → Reflect → Human decision → Outcome → Future memory**

No autonomous dispatch or emergency action is performed.

## Data source notes

The project uses public programmatic feeds where available. IMD documents that its warning ecosystem uses Common Alert Protocol and APIs, and NDMA's SACHET portal provides geo-targeted disaster alerts and an RSS feed. USGS publishes machine-readable real-time earthquake feeds. Open-Meteo provides continuously updated forecast/current-weather data from multiple national weather models. GDACS provides a public API for disaster-event data.

For production agency deployment, authorized agency feeds (for example an organization's authenticated IMD/NDMA/CWC/SACHET integration) should be configured rather than treating public aggregators as authoritative field status.

## How this uses Hindsight

CrisisOps uses one Hindsight memory bank, `crisisops-disaster-response-memory`, as its cross-incident semantic memory. A field report is **Retained** with its needs, resources, route constraints, attempted action, outcome, provenance and source type. When an operator submits a new response plan, the plan is sent to **Recall** so relevant prior incidents and observations can be surfaced. The result is then sent to **Reflect**, which produces structured decision support: recurring patterns, transport constraints, resource conflicts, evidence, recommended human checks and unanswered questions. The operator makes the final decision and can record the outcome, which becomes future memory. Live public-intelligence snapshots can also be explicitly retained.

### Provenance is part of the product

Every displayed data point belongs to one of three categories:

- **REAL** — read-only information retrieved from public feeds such as Open-Meteo, USGS, IMD CAP and GDACS.
- **OPERATOR INPUT** — information a human responder entered into CrisisOps.
- **SYNTHETIC** — deterministic demo/seed records used for the judging walkthrough.

Hindsight analyses are labelled **HINDSIGHT SYNTHESIS**; their underlying memories preserve the source type. A local similarity fallback is labelled **LOCAL DEMO FALLBACK** and is never presented as live Hindsight memory.

### Before / after demo

Use `POST /api/demo/seed` to load the canonical synthetic Incident A and Incident B. Incident A is retained; Incident B is deliberately left as the recall target. Then use `POST /api/demo/verify-loop` to execute Retain → Recall → Reflect and return a structured trace. The dashboard also exposes a side-by-side **Without memory / With memory** review and an analysis-history timeline.

The memory-free side of the demo uses a deterministic checklist built only from the current plan. This keeps the comparison focused on the effect of Hindsight rather than introducing a second model dependency.

### Demo honesty

The canonical incidents are synthetic. They are not represented as real victims or live agency reports. Public-feed values are shown with source and retrieval time, and operator-entered data stays distinct from those feeds.
