"""Thin client for the Devin REST API (v1 + v3 org endpoints).

Auth: set DEVIN_API_KEY (an API key from the org you want to run the eval in).
Optionally set DEVIN_ORG_ID (org-...) to enable v3 org endpoints for exact
per-session ACU readings; without it we fall back to best-effort fields on v1.
"""

from __future__ import annotations

import os
import time
import logging

import requests

BASE = os.environ.get("DEVIN_API_BASE", "https://api.devin.ai")

log = logging.getLogger("harness.api")


class DevinAPI:
    def __init__(self, api_key: str | None = None, org_id: str | None = None):
        self.api_key = api_key or os.environ["DEVIN_API_KEY"]
        self.org_id = org_id or os.environ.get("DEVIN_ORG_ID")
        self.s = requests.Session()
        self.s.headers["Authorization"] = f"Bearer {self.api_key}"

    def _req(self, method: str, path: str, retries: int = 4, **kw):
        for attempt in range(retries):
            r = self.s.request(method, f"{BASE}{path}", timeout=60, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                wait = 2**attempt * 5
                log.warning("HTTP %s on %s, retrying in %ss", r.status_code, path, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
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
        idempotent: bool = False,
    ) -> dict:
        body: dict = {"prompt": prompt, "idempotent": idempotent}
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
        return self._req("POST", "/v1/sessions", json=body)

    def get_session_v1(self, session_id: str) -> dict:
        return self._req("GET", f"/v1/session/{session_id}")

    def send_message(self, session_id: str, message: str) -> None:
        self._req("POST", f"/v1/session/{session_id}/message", json={"message": message})

    # ---- v3 org endpoints (exact ACUs) ----
    def get_session_v3(self, devin_id: str) -> dict | None:
        if not self.org_id:
            return None
        if not devin_id.startswith("devin-"):
            devin_id = f"devin-{devin_id}"
        try:
            return self._req("GET", f"/v3/organizations/{self.org_id}/sessions/{devin_id}")
        except requests.HTTPError as e:
            log.warning("v3 session fetch failed for %s: %s", devin_id, e)
            return None

    def get_acus(self, devin_id: str) -> float | None:
        """Exact ACUs for a session. Prefers v3 detail, falls back to consumption."""
        d = self.get_session_v3(devin_id)
        if d and d.get("acus_consumed") is not None:
            return float(d["acus_consumed"])
        if not self.org_id:
            return None
        if not devin_id.startswith("devin-"):
            devin_id = f"devin-{devin_id}"
        try:
            c = self._req(
                "GET", f"/v3/organizations/{self.org_id}/consumption/daily/sessions/{devin_id}"
            )
            return float(c["total_acus"])
        except requests.HTTPError:
            return None
