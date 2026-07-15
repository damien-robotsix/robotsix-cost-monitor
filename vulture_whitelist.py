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
reconcile_last
analyst_digest
analyst_proposals
analyst_run
analyst_run_targeted
analyst_targeted
index
analyst_page

# analyst.py — Pydantic model fields (consumed by pydantic BaseModel)
rationale
estimated_saving

# tests/test_reconcile.py — _FrozenNow.now(tz) mimics datetime.now interface
tz

# Pydantic model_config / field false-positives (clients/models.py)
model_config
total_cost
calculated_total_cost
