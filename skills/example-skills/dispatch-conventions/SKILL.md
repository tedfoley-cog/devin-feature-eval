---
name: dispatch-conventions
description: Conventions for adding models, fields, endpoints, and migrations in this Dispatch fork.
---

# Dispatch change conventions

- Each domain module (e.g. `src/dispatch/incident/`) contains `models.py`
  (SQLAlchemy model + Pydantic schemas together), `service.py` (business
  logic), `views.py` (FastAPI router). Mirror this structure exactly.
- New fields: update the SQLAlchemy model AND the Pydantic `*Create`/`*Update`/
  `*Read` models in the same `models.py`.
- Migrations: Alembic, revisions under `src/dispatch/database/revisions/tenant`.
  Generate with `alembic revision --autogenerate -m "..."`. Never run migrations
  against shared databases.
- Endpoints: register on the module router in `views.py`; auth via the standard
  dependencies used by neighboring endpoints; keep logic in `service.py`.
- Config values: read via `src/dispatch/config.py` (starlette Config), never
  `os.environ` directly.
