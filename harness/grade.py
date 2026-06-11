"""Grade collected results -> results/graded.jsonl.

QA tasks: each answer is checked against the answer key. Matching is
case-insensitive substring/keyword matching: an answer is correct if it
contains all `must_contain` terms (or any one of `accept_any`). Write keys
BEFORE running the eval and grade blind to arm.

Coding tasks: if a `grade_command` is configured for the task, it is executed
with env vars PR_URL / REPO / RUN_KEY and must exit 0 (pass) or non-zero
(fail), printing an optional float score 0..1 on the last stdout line.

Usage:
    python -m harness.grade --config config.yaml
"""

from __future__ import annotations

import os
import re
import sys
import json
import logging
import pathlib
import argparse
import subprocess

import yaml

from .tasks import load_task_instances

log = logging.getLogger("harness.grade")
ROOT = pathlib.Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results" / "results.jsonl"
GRADED = ROOT / "results" / "graded.jsonl"


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9_./-]+", " ", (s or "").lower()).strip()


def grade_qa(task: dict, structured: dict | None) -> dict:
    answers = structured or {}
    per_q = []
    for j, q in enumerate(task["questions"]):
        a = norm(str(answers.get(f"answer_{j+1}", "")))
        if "accept_any" in q:
            ok = any(norm(t) in a for t in q["accept_any"])
        else:
            ok = all(norm(t) in a for t in q.get("must_contain", []))
        per_q.append(ok)
    score = sum(per_q) / len(per_q) if per_q else 0.0
    return {"score": score, "per_question": per_q, "success": score >= 0.8}


def grade_coding(task: dict, rec: dict) -> dict:
    pr_url = None
    so = rec.get("structured_output") or {}
    pr_url = so.get("pr_url")
    if not pr_url and rec.get("pull_requests"):
        prs = rec["pull_requests"]
        pr_url = prs[0]["pr_url"] if isinstance(prs, list) else prs.get("url")
    if not pr_url:
        return {"score": 0.0, "success": False, "reason": "no PR produced"}
    cmd = task.get("grade_command")
    if not cmd:
        return {"score": None, "success": None, "pr_url": pr_url, "reason": "no grade_command; grade manually"}
    env = {**os.environ, "PR_URL": pr_url, "RUN_KEY": rec["run_key"]}
    p = subprocess.run(cmd, shell=True, env=env, capture_output=True, text=True, timeout=3600)
    score = 1.0 if p.returncode == 0 else 0.0
    last = (p.stdout.strip().splitlines() or [""])[-1]
    try:
        score = float(last)
    except ValueError:
        pass
    return {"score": score, "success": score >= 0.8, "pr_url": pr_url, "grader_exit": p.returncode}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    cfg = yaml.safe_load((ROOT / args.config).read_text())
    tasks_by_id: dict[str, dict] = {}
    for exp in cfg["experiments"]:
        for t in load_task_instances(ROOT / exp["task_file"]):
            tasks_by_id[t["id"]] = t

    already = set()
    if GRADED.exists():
        already = {json.loads(l)["run_key"] for l in GRADED.read_text().splitlines() if l.strip()}

    with GRADED.open("a") as out:
        for line in RESULTS.read_text().splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec["run_key"] in already:
                continue
            task = tasks_by_id.get(rec["task_id"])
            if not task:
                log.warning("no task spec for %s", rec["task_id"])
                continue
            g = grade_qa(task, rec.get("structured_output")) if task["type"] == "qa" else grade_coding(task, rec)
            out.write(json.dumps({**rec, **g}) + "\n")
            log.info("graded %s score=%s", rec["run_key"], g.get("score"))


if __name__ == "__main__":
    sys.exit(main())
