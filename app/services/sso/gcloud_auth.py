"""Google Cloud / Google Workspace SSO (OAuth2 OIDC).

Supports:
- Google Workspace hd (hosted domain) restriction
- G-Cloud IAM (GCP project service accounts)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import urllib.parse

import httpx

from app.storage.sso_store import GCloudConfig


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def build_gcloud_auth_url(config: GCloudConfig, redirect_uri: str) -> tuple[str, str]:
    """Build Google OAuth2 authorization URL.

    Returns (auth_url, state).
    """
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": config.client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account",
    }
    if config.hd:
        params["hd"] = config.hd
    auth_url = GOOGLE_AUTH_URL + "?" + urllib.parse.urlencode(params)
    return auth_url, state


def exchange_gcloud_code(config: GCloudConfig, code: str, redirect_uri: str) -> dict | None:
    """Exchange authorization code for user info.

    Returns dict with keys: username, display_name, email, role, hd
    Returns None on failure.
    """
    # Exchange code for token
    try:
        token_resp = httpx.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }, timeout=10)
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception:
        return None

    access_token = token_data.get("access_token")
    if not access_token:
        return None

    # Get user info
    try:
        user_resp = httpx.get(GOOGLE_USERINFO_URL,
                              headers={"Authorization": f"Bearer {access_token}"},
                              timeout=10)
        user_resp.raise_for_status()
        user_info = user_resp.json()
    except Exception:
        return None

    email = user_info.get("email", "")
    hd = user_info.get("hd", "")  # hosted domain from Google

    # Domain restriction
    if config.hd and hd != config.hd:
        return None
    if config.allowed_domains:
        email_domain = email.split("@")[-1] if "@" in email else ""
        if email_domain not in config.allowed_domains:
            return None

    display_name = user_info.get("name") or email
    return {
        "username": email,
        "display_name": display_name,
        "email": email,
        "role": config.default_role,
        "hd": hd,
    }
