"""Thin client for the Devin REST API (v3 org endpoints only).

Auth: set DEVIN_API_KEY (an API key from the org you want to run the eval in)
and DEVIN_ORG_ID (org-... id). All endpoints are org-scoped v3 routes, which
also return exact per-session ACU readings (`acus_consumed`).
"""

from __future__ import annotations

import os
import time
import logging

import requests

BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai")

log = logging.getLogger("harness.api")

# v3 session statuses: new, claimed, running, exit, error, suspended, resuming.
# A session is "settled" when it has stopped doing work: terminal statuses, or
# running with a terminal/blocked status_detail.
SETTLED_STATUSES = {"exit", "error", "suspended"}
SETTLED_DETAILS = {"finished", "waiting_for_user", "waiting_for_approval"}


def is_settled(session: dict) -> bool:
    status = session.get("status")
    if status in SETTLED_STATUSES:
        return True
    return status == "running" and session.get("status_detail") in SETTLED_DETAILS


def _devin_id(session_id: str) -> str:
    return session_id if session_id.startswith("devin-") else f"devin-{session_id}"


class DevinAPI:
    def __init__(self, api_key: str | None = None, org_id: str | None = None):
        self.api_key = api_key or os.environ["DEVIN_API_KEY"]
        self.org_id = org_id or os.environ["DEVIN_ORG_ID"]
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.api_key}"

    def _req(self, method: str, path: str, retries: int = 4, **kw):
        last_exc: Exception | None = None
        for attempt in range(retries):
            try:
                r = self.s.request(method, f"{BASE}{path}", timeout=60, **kw)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                wait = 2**attempt * 5
                log.warning("%s on %s, retrying in %ss", type(e).__name__, path, wait)
                time.sleep(wait)
                continue
            last_exc = None
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 2**attempt * 5
                log.warning("HTTP %s on %s, retrying in %ss", r.status_code, path, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        if last_exc is not None:
            raise last_exc
        r.raise_for_status()

    # ---- sessions ----
    def create_session(
        self,
        prompt: str,
        *,
        title: str | None = None,
        playbook_id: str | None = None,
        tags: list[str] | None = None,
        structured_output_schema: dict | None = None,
        max_acu_limit: int | None = None,
    ) -> dict:
        body: dict = {"prompt": prompt}
        if title:
            body["title"] = title
        if playbook_id:
            body["playbook_id"] = playbook_id
        if tags:
            body["tags"] = tags
        if structured_output_schema:
            body["structured_output_schema"] = structured_output_schema
        if max_acu_limit:
            body["max_acu_limit"] = max_acu_limit
        return self._req("POST", f"/v3/organizations/{self.org_id}/sessions", json=body)

    def get_session(self, session_id: str) -> dict:
        return self._req(
            "GET", f"/v3/organizations/{self.org_id}/sessions/{_devin_id(session_id)}"
        )

    def send_message(self, session_id: str, message: str) -> None:
        self._req(
            "POST",
            f"/v3/organizations/{self.org_id}/sessions/{_devin_id(session_id)}/messages",
            json={"message": message},
        )

    def get_acus(self, session_id: str) -> float | None:
        """Exact ACUs for a session. Prefers session detail, falls back to consumption."""
        try:
            d = self.get_session(session_id)
            if d.get("acus_consumed") is not None:
                return float(d["acus_consumed"])
        except requests.HTTPError as e:
            log.warning("v3 session fetch failed for %s: %s", session_id, e)
        try:
            c = self._req(
                "GET",
                f"/v3/organizations/{self.org_id}/consumption/daily/sessions/{_devin_id(session_id)}",
            )
            return float(c["total_acus"])
        except requests.HTTPError:
            return None
