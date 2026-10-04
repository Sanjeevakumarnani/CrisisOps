# Architecture Overview

CrisisOps is organized around a human-in-the-loop operational memory loop:

```
Public signals / field reports
          |
          v
      Capture layer
          |
          v
  Provenance-aware records
          |
          v
   Retain / persistent memory
          |
          v
     Recall similar history
          |
          v
   Reflect / decision support
          |
          v
      Human decision
          |
          v
   Outcome / future memory
```

## Data provenance

Every displayed operational signal is classified as one of:

- **REAL** — retrieved from a public external feed such as Open-Meteo, USGS, IMD CAP, or GDACS.
- **OPERATOR INPUT** — entered by a human responder.
- **SYNTHETIC** — deterministic records used for demonstrations and testing.

The UI preserves source and retrieval time so external intelligence is not confused with verified field status.

## Memory layer

Hindsight provides the persistent semantic memory path:

1. **Retain** a normalized incident, observation, plan, or outcome.
2. **Recall** relevant historical memories for a proposed response plan.
3. **Reflect** on recurring patterns, constraints, conflicts, evidence, and unanswered questions.
4. Keep the final decision with the human operator.

When Hindsight credentials are unavailable, the application uses an explicitly labelled local demo fallback.

## Safety boundary

CrisisOps is decision support. It does not autonomously dispatch responders, alter routes, or assert unverified live facts.

## Repository map

```
app/             API and application logic
static/          Web dashboard assets
data/            Demo and seed data
tests/           Automated validation
Dockerfile       Container deployment
render.yaml      Render deployment configuration
```

## Demo path

The canonical demonstration compares a plan reviewed without memory against the same plan reviewed with retained incident history. The comparison is designed to show the value of operational memory without presenting synthetic incidents as real events.
