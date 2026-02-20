import os
from typing import Any

import httpx


class StatuspageError(Exception):
    pass


class StatuspageClient:
    def __init__(self, base_url: str = "https://api.statuspage.io/v1") -> None:
        self.base_url = base_url.rstrip("/")

    def _credentials(self) -> tuple[str, str]:
        page_id = os.getenv("STATUSPAGE_PAGE_ID", "").strip()
        api_key = os.getenv("STATUSPAGE_API_KEY", "").strip()
        if not page_id or not api_key:
            raise StatuspageError("Status page notification failed.")
        return page_id, api_key

    def create_investigating_incident(self, *, stage: str, incident_key: str) -> dict[str, str]:
        page_id, api_key = self._credentials()
        url = f"{self.base_url}/pages/{page_id}/incidents"
        body = {
            "incident": {
                "name": "Investigating elevated errors/latency",
                "status": "investigating",
                "body": (
                    "We are investigating. Next update in 30 minutes. "
                    "Request IDs available on request."
                ),
                "metadata": {"stage": stage, "incident_key": incident_key},
            }
        }
        headers = {
            "Authorization": f"OAuth {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise StatuspageError("Status page notification failed.")
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise StatuspageError("Status page notification failed.")

        incident_id = payload.get("id")
        if not isinstance(incident_id, str) or not incident_id.strip():
            incident = payload.get("incident")
            if isinstance(incident, dict):
                candidate = incident.get("id")
                if isinstance(candidate, str) and candidate.strip():
                    incident_id = candidate
        if not isinstance(incident_id, str) or not incident_id.strip():
            raise StatuspageError("Status page notification failed.")

        incident_url = payload.get("shortlink")
        if not isinstance(incident_url, str) or not incident_url.strip():
            incident_url = incident_id
        return {"incident_id": incident_id, "incident_url": incident_url}

    def post_investigating_update(self, *, incident_id: str) -> None:
        page_id, api_key = self._credentials()
        url = f"{self.base_url}/pages/{page_id}/incidents/{incident_id}/incident_updates"
        body = {
            "incident_update": {
                "status": "investigating",
                "body": "Still investigating elevated errors/latency. Next update in 30 minutes.",
                "wants_twitter_update": False,
                "wants_email": False,
            }
        }
        headers = {
            "Authorization": f"OAuth {api_key}",
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, headers=headers, json=body)
        if response.status_code >= 400:
            raise StatuspageError("Status page notification failed.")
