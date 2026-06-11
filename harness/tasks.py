"""Task file loading.

Task files are YAML with a `type` of:
- qa:     a set of comprehension questions with an answer key. One task
          instance bundles `questions_per_session` questions; the session
          returns answers via structured output.
- coding: a concrete engineering task; accuracy is graded by a command run
          against the resulting PR (see grade.py) and/or an LLM-judge rubric.
"""

from __future__ import annotations

import pathlib

import yaml

QA_PROMPT = """Answer the following questions about the repository {repo} (branch {branch}).
Work autonomously and do not ask the user anything. Investigate the codebase as
needed, then provide your final answers in the structured output. Keep each
answer short and specific (file paths, function names, or 1-2 sentences).

{questions}
"""


def load_task_instances(path: pathlib.Path) -> list[dict]:
    spec = yaml.safe_load(path.read_text())
    if spec["type"] == "qa":
        per = spec.get("questions_per_session", 5)
        qs = spec["questions"]
        instances = []
        for i in range(0, len(qs), per):
            chunk = qs[i : i + per]
            qtext = "\n".join(f"{j+1}. {q['q']}" for j, q in enumerate(chunk))
            instances.append(
                {
                    "id": f"{spec['id']}-{i//per}",
                    "type": "qa",
                    "prompt": QA_PROMPT.replace("{questions}", qtext),
                    "questions": chunk,
                }
            )
        return instances
    if spec["type"] == "coding":
        return [
            {
                "id": t["id"],
                "type": "coding",
                "prompt": t["prompt"],
                "grade_command": t.get("grade_command", spec.get("grade_command")),
                "rubric": t.get("rubric"),
            }
            for t in spec["tasks"]
        ]
    raise ValueError(f"unknown task type {spec['type']}")


def build_schema(task: dict) -> dict | None:
    if task["type"] == "qa":
        props = {
            f"answer_{j+1}": {"type": "string", "description": q["q"]}
            for j, q in enumerate(task["questions"])
        }
        return {"type": "object", "properties": props, "required": list(props)}
    if task["type"] == "coding":
        return {
            "type": "object",
            "properties": {
                "pr_url": {"type": "string", "description": "URL of the pull request created"},
                "summary": {"type": "string", "description": "One-paragraph summary of changes"},
            },
            "required": ["pr_url"],
        }
    return None
