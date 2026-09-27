# CrisisOps — Disaster Response Memory Engine

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
