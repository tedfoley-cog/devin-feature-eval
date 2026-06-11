"""Collect results for launched runs.

Usage:
    python -m harness.collect [--watch]

Polls every launched session until it settles (exit/error/suspended, or running
with a finished/blocked status_detail), then records status, ACUs, structured
output, PRs and timing into
results/results.jsonl. Safe to re-run; already-collected runs are skipped.
"""

from __future__ import annotations

import sys
import json
import time
import logging
import pathlib
import argparse

from .devin_api import DevinAPI, is_settled

log = logging.getLogger("harness.collect")
ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "results" / "runs.jsonl"
RESULTS = ROOT / "results" / "results.jsonl"


def jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--watch", action="store_true", help="keep polling until all runs settle")
    ap.add_argument("--interval", type=int, default=120)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    api = DevinAPI()
    while True:
        runs = jsonl(RUNS)
        done = {r["run_key"] for r in jsonl(RESULTS)}
        pending = [r for r in runs if r["run_key"] not in done]
        if not pending:
            log.info("all %d runs collected", len(runs))
            return
        log.info("%d/%d runs pending", len(pending), len(runs))
        for r in pending:
            sid = r["session_id"]
            d = api.get_session(sid)
            if not is_settled(d):
                continue
            status = d.get("status")
            acus = d.get("acus_consumed")
            acus = float(acus) if acus is not None else api.get_acus(sid)
            rec = {
                **{k: r[k] for k in ("run_key", "experiment", "arm", "task_id", "rep", "session_id", "url")},
                "status": status,
                "status_detail": d.get("status_detail"),
                "acus": acus,
                "structured_output": d.get("structured_output"),
                "pull_requests": d.get("pull_requests"),
                "created_at": d.get("created_at"),
                "updated_at": d.get("updated_at"),
                "collected_at": int(time.time()),
            }
            with RESULTS.open("a") as f:
                f.write(json.dumps(rec) + "\n")
            log.info("collected %s status=%s acus=%s", r["run_key"], status, acus)
        if not args.watch:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
