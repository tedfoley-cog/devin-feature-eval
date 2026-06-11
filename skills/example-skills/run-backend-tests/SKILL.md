---
name: run-backend-tests
description: How to set up and run the Dispatch backend test suite locally.
---

# Running the Dispatch backend tests

1. Install dev deps: `pip install -e ".[dev]"` from the repo root.
2. Tests need no live Postgres: the suite uses fixtures in `tests/conftest.py`.
3. Run: `pytest tests/ -x -q`. A single module: `pytest tests/incident -x -q`.
4. Use factories from `tests/factories.py` when writing new tests — never build
   model instances by hand.
5. Lint before committing: `pre-commit run --all-files`.
