# Playbook: Make a model/API change in the Dispatch fork

(Create this as a playbook in your org and put its `playbook-...` id in
config.yaml. Body below.)

## Overview
You are making a backend change in our Dispatch fork (FastAPI + SQLAlchemy + Alembic + pytest, frontend Vue under `src/dispatch/static/dispatch`).

## What's needed from the user
- The specific change to make (field, endpoint, or bug to fix) and target branch.

## Procedure
1. Work off the branch named in the prompt; create a feature branch; never push to it directly.
2. Read the relevant module first: models live next to their `service.py`, Pydantic schemas in `models.py`, routers in `views.py`. Follow an existing nearby example end-to-end before writing code.
3. For model changes: update the SQLAlchemy model, the Pydantic Create/Update/Read models, and generate an Alembic revision under `src/dispatch/database/revisions/tenant` using `alembic revision --autogenerate`. Never apply migrations to any shared/hosted database.
4. For endpoints: add to the module's `views.py` router with the standard auth dependencies, business logic in `service.py`, no logic in the view.
5. Tests: use the factories in `tests/factories.py`; run the suite with `pytest tests/ -x -q` before opening the PR.
6. Open a PR into the branch named in the prompt with a concise summary.

## Specs
- Work fully autonomously; do not ask the user questions.
- PR must pass `pytest tests/` locally before creation.

## Forbidden actions
- Do not modify unrelated files, do not upgrade dependencies, do not touch CI config.
