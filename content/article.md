# CrisisOps: A Disaster Response System That Remembers

A disaster-response dashboard is useful only if the information on it is current, traceable and connected to what happened before. In a fast-moving incident, a route can close, a shelter can fill, a resource can become committed, or a previous intervention can fail for a reason that is easy to forget. CrisisOps is designed around that operational gap: combine current public hazard intelligence and human field reports with persistent memory so responders can review history before making the next decision.

## The problem: a dashboard without memory resets the team

Traditional operational dashboards are good at showing the current state. They are much weaker at preserving the reasoning and lessons behind previous actions. A new incident commander may see that water is needed at a location, but not know that a previous road delivery was blocked by flooding, that a particular resource was already committed elsewhere, or that an alternative intervention worked under similar conditions.

CrisisOps represents each field report as a structured operational event. It records the location, time, urgency, affected people, needs, resources, responders, transport constraints, operational conditions, attempted actions, outcome and source. That information is retained as durable memory instead of disappearing into an isolated incident screen.

## Real external intelligence + human operational truth

The prototype is no longer limited to a synthetic dashboard. The main screen includes live public data feeds:

- current weather and short-horizon weather conditions from Open-Meteo;
- India Meteorological Department CAP alert messages;
- the USGS past-day earthquake feed, filtered around the selected operating location;
- GDACS public disaster-event data when available.

The important distinction is provenance. These feeds are labelled as public external intelligence. They are not silently converted into “verified field status.” Human-entered field reports remain a separate operational layer.

For example, the dashboard can show a current weather signal for Hyderabad while a responder enters a field report that a particular road is waterlogged. The system keeps those facts separate, timestamps them and records their sources.

## Where Hindsight changes the workflow

Hindsight provides the persistent memory layer. CrisisOps uses the three core memory operations as a visible operational loop:

**Retain → Recall → Reflect**

A new field event is retained with a stable document identifier, timestamp, source and tags. When a response plan is submitted, CrisisOps recalls relevant historical memories and then asks Hindsight to reflect across those memories. The resulting review is structured into risk, recurring patterns, resource conflicts, transport constraints, recommended human checks, unanswered questions and evidence.

The application can also explicitly retain the current public-feed snapshot. This means a live weather or hazard signal can become part of the historical record rather than being useful only for the few minutes it is visible on the dashboard.

A simplified version of the memory capture looks like this:

```python
await client.aretain(
    bank_id=BANK_ID,
    content=live_signal,
    context="live public hazard data",
    timestamp=observed_at,
    document_id=stable_signal_id,
    tags=["source:usgs", "type:earthquake"],
)
```

Stable document IDs matter because the same source item can be updated without creating uncontrolled duplicate memories. CrisisOps uses deterministic IDs for live signals and incident records.

## Before and after memory

The central demonstration is deliberately simple.

**Before memory:**  
“Verify current needs, check routes, allocate resources and coordinate responders.”

That advice is reasonable but generic.

**After memory:**  
CrisisOps can retrieve previous incidents with similar locations, constraints or resource requirements. Hindsight can then synthesize patterns such as repeated route failures, recurring shortages, successful interventions and unresolved uncertainty.

The responder still makes the decision. CrisisOps is not an autonomous dispatch system and does not send people, change routes or claim that someone is safe without evidence.

## Why the interface is an operations console

The UI is intentionally not a chatbot. The first screen shows a common operational picture, current public intelligence, field signals and a memory layer. A responder can move from a live signal to a field report, then to a response-plan review without leaving the operational context.

The memory review page exposes the actual difference between a generic answer and a memory-backed answer. This makes Hindsight visible rather than treating it as an invisible implementation detail.

The system also exposes source and timestamp information because emergency decisions should be auditable. A public weather model, an official CAP alert and a human field report are not equivalent evidence, and the UI should not pretend that they are.

## The learning loop

CrisisOps is designed around a continuous loop:

**Capture → Retain → Recall → Reflect → Human decision → Outcome → Future memory**

Suppose a team proposes moving supplies through a particular corridor. Historical memory reveals that similar deliveries were previously blocked under certain conditions. The responder changes the plan, records the outcome, and the resulting event is retained. On a later incident, that experience becomes searchable again.

This is the core value of persistent memory: the system does not simply answer the current question. It makes previous operational experience available to the next decision.

## Limitations and next steps

The current prototype intentionally avoids pretending to be a complete emergency-management platform. Public feeds can be delayed, incomplete or unavailable. Open weather models are not a replacement for agency-specific forecasts. Public earthquake feeds are not a local incident-management system. GDACS provides global event intelligence, not verified local ground truth.

A production deployment would add authenticated agency integrations, role-based access control, immutable audit trails, stronger geospatial filtering, offline/mobile field workflows, secure incident identities, encrypted sensitive data, notification policies, disaster-specific SOP libraries and resilient infrastructure.

The prototype also uses synthetic operational records for the repeatable demonstration. That data is clearly labelled as synthetic; live public intelligence is shown separately. This prevents the demo from presenting invented victims, resources or responder positions as real-world facts.

The result is a practical memory-first response architecture: real external signals provide current context, human reports provide operational truth, and Hindsight connects today’s decision with yesterday’s experience.