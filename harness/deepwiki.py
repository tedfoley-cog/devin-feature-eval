"""DeepWiki client used for the 'ask-devin prompt generation' treatment arm.

Two backends:
- public:  https://mcp.deepwiki.com (public OSS wikis, no auth)
- private: Devin DeepWiki MCP via api.devin.ai (private repos in your org)

Both speak MCP streamable-HTTP; we issue a single `ask_question` tool call.
"""

from __future__ import annotations

import os
import json
import itertools

import requests

PUBLIC_MCP = "https://mcp.deepwiki.com/mcp"
PRIVATE_MCP = os.environ.get("DEEPWIKI_PRIVATE_MCP", "https://mcp.devin.ai/mcp")

_id = itertools.count(1)

PROMPT_GEN_TEMPLATE = """You are preparing a task prompt for an autonomous software engineering agent
(Devin) that will work on the repository {repo}.

Using your knowledge of this repository's architecture, write a single detailed,
self-contained implementation prompt for the following task. Ground the prompt in
the actual codebase: name the specific files, modules, functions, conventions and
test commands the agent should use. Do not solve the task; produce only the prompt.

TASK:
{task}
"""


def _mcp_call(url: str, tool: str, args: dict, headers: dict | None = None) -> str:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        **(headers or {}),
    }
    body = {
        "jsonrpc": "2.0",
        "id": next(_id),
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }
    r = requests.post(url, json=body, headers=h, timeout=300)
    r.raise_for_status()
    text = r.text
    # streamable HTTP may return SSE; extract the last data: line
    if "data:" in text and not text.lstrip().startswith("{"):
        lines = [l[5:].strip() for l in text.splitlines() if l.startswith("data:")]
        text = lines[-1]
    payload = json.loads(text)
    if "error" in payload:
        raise RuntimeError(f"MCP error: {payload['error']}")
    content = payload["result"]["content"]
    return "\n".join(c.get("text", "") for c in content)


def ask_question(repo: str, question: str, *, private: bool = False) -> str:
    if private:
        headers = {"Authorization": f"Bearer {os.environ['DEVIN_API_KEY']}"}
        return _mcp_call(PRIVATE_MCP, "ask_question", {"repoName": repo, "question": question}, headers)
    return _mcp_call(PUBLIC_MCP, "ask_question", {"repoName": repo, "question": question})


def generate_prompt(repo: str, task: str, *, private: bool = False) -> str:
    """The 'Ask Devin -> Devin' arm: have DeepWiki write a grounded prompt for the task."""
    return ask_question(repo, PROMPT_GEN_TEMPLATE.format(repo=repo, task=task), private=private)
