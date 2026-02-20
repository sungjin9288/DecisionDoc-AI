import os
from typing import Any

import httpx


class StatuspageClient:
    def __init__(self, base_url: str = "https://api.statuspage.io/v1") -> None:
        self.base_url = base_url.rstrip("/")

    def create_investigating_incident(self, *, stage: str, incident_id: str) -> str | None:
        page_id = os.getenv("STATUSPAGE_PAGE_ID", "").strip()
        api_key = os.getenv("STATUSPAGE_API_KEY", "").strip()
        if not page_id or not api_key:
            return None

        url = f"{self.base_url}/pages/{page_id}/incidents"
        body = {
            "incident": {
                "name": "Investigating elevated errors/latency",
                "status": "investigating",
                "body": (
                    "We are investigating. Next update in 30 minutes. "
                    "Request IDs available on request."
                ),
                "metadata": {"stage": stage, "incident_id": incident_id},
            }
        }
        headers = {
            "Authorization": f"OAuth {api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, headers=headers, json=body)
            if response.status_code >= 400:
                return None
            payload: Any = response.json()
            if not isinstance(payload, dict):
                return None
            shortlink = payload.get("shortlink")
            if isinstance(shortlink, str) and shortlink.strip():
                return shortlink
            incident = payload.get("incident")
            if isinstance(incident, dict):
                incident_id_value = incident.get("id")
                if isinstance(incident_id_value, str) and incident_id_value.strip():
                    return incident_id_value
            return None
        except Exception:
            return None
