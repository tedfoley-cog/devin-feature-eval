"""Launch eval sessions.

Usage:
    python -m harness.launch --config config.yaml [--experiment NAME] [--dry-run] [--pilot N]

Reads the experiment config, expands (experiment x arm x task-instance x rep)
into a run plan, interleaves arms (so no arm is time-clustered), creates Devin
sessions via the API, and records every launched run in results/runs.jsonl.

Resumable: runs already present in runs.jsonl (same run_key) are skipped.
"""

from __future__ import annotations

import sys
import json
import time
import logging
import pathlib
import argparse

import yaml

from .devin_api import DevinAPI
from . import deepwiki
from .tasks import load_task_instances, build_schema

log = logging.getLogger("harness.launch")
ROOT = pathlib.Path(__file__).resolve().parent.parent
RUNS = ROOT / "results" / "runs.jsonl"


def load_existing() -> set[str]:
    if not RUNS.exists():
        return set()
    return {json.loads(l)["run_key"] for l in RUNS.read_text().splitlines() if l.strip()}


def append_run(rec: dict) -> None:
    RUNS.parent.mkdir(exist_ok=True)
    with RUNS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def build_prompt(arm: dict, task: dict, exp: dict) -> str:
    mode = arm.get("prompt_mode", "raw")
    base = task["prompt"].format(repo=arm["repo"], branch=arm.get("branch", "main"))
    if mode == "raw":
        return base
    if mode == "playbook":
        # playbook content is attached via playbook_id at session creation;
        # the prompt carries only the task-specific parameters.
        return base
    if mode == "deepwiki_prompt":
        log.info("  generating prompt via DeepWiki ask_question for %s", arm["repo"])
        generated = deepwiki.generate_prompt(
            arm.get("wiki_repo", arm["repo"]), base, private=arm.get("private_wiki", False)
        )
        # Keep the original task + output contract; DeepWiki output is guidance.
        return (
            f"{base}\n\n---\nA repository expert prepared the following implementation "
            f"guidance for this exact task. Follow it where it is correct:\n\n{generated}"
        )
    raise ValueError(f"unknown prompt_mode {mode}")


def plan_runs(cfg: dict, only_exp: str | None, pilot: int | None) -> list[dict]:
    plan = []
    defaults = cfg.get("defaults", {})
    for exp in cfg["experiments"]:
        if only_exp and exp["name"] != only_exp:
            continue
        reps = pilot or exp.get("reps", defaults.get("reps", 8))
        tasks = load_task_instances(ROOT / exp["task_file"])
        for task in tasks:
            for rep in range(reps):
                for arm in exp["arms"]:
                    plan.append(
                        {
                            "experiment": exp["name"],
                            "arm": arm["name"],
                            "task_id": task["id"],
                            "rep": rep,
                            "run_key": f"{exp['name']}/{task['id']}/{arm['name']}/r{rep}",
                            "_arm": arm,
                            "_task": task,
                            "_exp": exp,
                        }
                    )
    # interleave: sort by (task, rep) then arm order is already round-robin per rep
    plan.sort(key=lambda r: (r["experiment"], r["task_id"], r["rep"]))
    return plan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--experiment")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pilot", type=int, help="override reps for a small pilot run")
    ap.add_argument("--max-inflight", type=int, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    defaults = cfg.get("defaults", {})
    max_inflight = args.max_inflight or defaults.get("concurrency", 6)
    existing = load_existing()
    plan = plan_runs(cfg, args.experiment, args.pilot)
    todo = [r for r in plan if r["run_key"] not in existing]
    log.info("plan: %d runs total, %d already launched, %d to launch", len(plan), len(existing), len(todo))

    if args.dry_run:
        for r in todo:
            print(r["run_key"])
        return

    api = DevinAPI()
    inflight: list[str] = []

    def wait_capacity():
        while len(inflight) >= max_inflight:
            time.sleep(30)
            for sid in list(inflight):
                st = api.get_session_v1(sid).get("status_enum") or api.get_session_v1(sid).get("status")
                if st in ("blocked", "stopped", "finished", "expired", "exit", "suspended"):
                    inflight.remove(sid)

    for r in todo:
        wait_capacity()
        arm, task, exp = r["_arm"], r["_task"], r["_exp"]
        prompt = build_prompt(arm, task, exp)
        schema = build_schema(task)
        tags = ["feature-eval", r["experiment"], f"arm:{r['arm']}", f"task:{r['task_id']}", f"rep:{r['rep']}"]
        resp = api.create_session(
            prompt,
            title=f"[eval] {r['run_key']}",
            playbook_id=arm.get("playbook_id"),
            tags=tags,
            structured_output_schema=schema,
            max_acu_limit=exp.get("max_acu_limit", defaults.get("max_acu_limit")),
        )
        sid = resp["session_id"]
        inflight.append(sid)
        append_run(
            {
                "run_key": r["run_key"],
                "experiment": r["experiment"],
                "arm": r["arm"],
                "task_id": r["task_id"],
                "rep": r["rep"],
                "session_id": sid,
                "url": resp.get("url"),
                "prompt": prompt,
                "launched_at": int(time.time()),
            }
        )
        log.info("launched %s -> %s", r["run_key"], resp.get("url"))
        time.sleep(defaults.get("launch_spacing_s", 20))


if __name__ == "__main__":
    sys.exit(main())
