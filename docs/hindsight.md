# Hindsight memory design

CrisisOps stores durable response events in the `crisisops-disaster-response-memory` bank. Each retained event keeps its needs, resources, responders, transport constraints, operational conditions, attempted actions, outcome, provenance and source type.

## Retain
Field reports and opted-in public-intelligence snapshots are retained with stable document IDs and source metadata. Synthetic demo records are tagged `source_type:synthetic`; human-entered reports are tagged `source_type:operator`; public feeds are tagged `source_type:real`.

## Recall
Before a response plan is reviewed, CrisisOps builds a query from the current objective, location, resources, transport plan, constraints, proposed actions and context. Hindsight returns semantically relevant operational history.

## Reflect
The recalled history is passed to Hindsight reflection. The structured response contains risk level, confidence, summary, recalled evidence, recurring patterns, resource conflicts, transport constraints, recommended human checks, unanswered questions and evidence.

## Canonical demo
Incident A is a synthetic North Ward flooding record: 120 people affected, water and medical-support needs, bridge closed, road delivery attempted, route became inaccessible. Incident B is a synthetic follow-up plan: 150 people affected, 2 boats + 1 truck, Bridge 4 closed, proposed canal route. The verify-loop endpoint retains A, recalls it while reviewing B, and returns a trace that shows which expected evidence surfaced.

## Honesty / fallback
The UI distinguishes REAL public intelligence, OPERATOR INPUT, and SYNTHETIC demo records. If Hindsight is unavailable, local similarity is labeled `LOCAL DEMO FALLBACK` and is never presented as persistent Hindsight memory.
