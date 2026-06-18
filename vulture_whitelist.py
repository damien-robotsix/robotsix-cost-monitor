"""Whitelist for vulture dead-code detection.

False positives that vulture cannot resolve through static analysis alone:
FastAPI route handlers (registered via decorators), a uvicorn factory function
(called via string reference in cli.py), and Pydantic model fields (used by
pydantic internals).
"""

# app.py — FastAPI route handlers and factory function
create_app  # called via string reference in cli.py (uvicorn --factory)
health
reconcile
analyst_digest
analyst_proposals
analyst_run
index

# analyst.py — Pydantic model fields (consumed by pydantic BaseModel)
rationale
estimated_saving
