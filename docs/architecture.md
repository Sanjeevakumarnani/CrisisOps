# CrisisOps architecture

CrisisOps is a FastAPI + SQLite operational picture with a Hindsight memory layer.

Flow: field report → structured event → local operational store → Hindsight retain → recall → plan review → human decision → outcome → future memory.

The application never dispatches responders, changes routes, or claims live truth. Human confirmation remains required.
