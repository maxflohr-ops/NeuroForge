#!/usr/bin/env python3
"""
Ayrshare Profiles Agent (Business plan)
Onboards clipping-community members: each gets an Ayrshare User Profile and a
single-sign-on link where they connect their OWN socials (no shared passwords).
The bot can then post through their profiles via the Profile-Key header.

Flow (per the Ayrshare Business integration guide, domain id-4-GaO):
    POST /profiles                  → create a User Profile (returns profileKey)
    POST /profiles/generateJWT      → domain + private key (+ profileKey)
                                      → 5-minute SSO URL for the member
"""

from pathlib import Path

import requests

from .config import Config


class AyrshareProfileError(RuntimeError):
    pass


class ProfileManager:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {config.ayrshare_api_key}"})

    def _url(self, path: str) -> str:
        return f"{self.config.ayrshare_api_base.rstrip('/')}/{path.lstrip('/')}"

    def _private_key(self) -> str:
        path = Path(self.config.ayrshare_private_key_file)
        if not path.exists():
            raise AyrshareProfileError(
                f"Ayrshare private key not found at {path} — it ships in the "
                "Business integration package (id-<domain>-private-key.key)")
        return path.read_text()

    def create_profile(self, title: str) -> dict:
        """Create a User Profile for a community member. SAVE the returned
        profileKey — Ayrshare only reveals it at creation time."""
        resp = self.session.post(self._url("/profiles"),
                                 json={"title": title}, timeout=60)
        data = resp.json()
        if resp.status_code != 200 or data.get("status") == "error":
            raise AyrshareProfileError(
                f"profile create failed ({resp.status_code}): {resp.text[:500]}")
        return data

    def list_profiles(self) -> list:
        resp = self.session.get(self._url("/profiles"), timeout=60)
        if resp.status_code != 200:
            raise AyrshareProfileError(
                f"profile list failed ({resp.status_code}): {resp.text[:500]}")
        data = resp.json()
        return data.get("profiles", data if isinstance(data, list) else [])

    def generate_sso_url(self, profile_key: str) -> str:
        """Generate the social-linking SSO URL for a member (valid ~5 minutes,
        so send it right away)."""
        if not self.config.ayrshare_domain:
            raise AyrshareProfileError("AYRSHARE_DOMAIN is not set (e.g. id-4-GaO)")
        resp = self.session.post(
            self._url("/profiles/generateJWT"),
            data={
                "domain": self.config.ayrshare_domain,
                "privateKey": self._private_key(),
                "profileKey": profile_key,
                "verify": "true",
            },
            timeout=60)
        data = resp.json()
        if resp.status_code != 200 or data.get("status") == "error":
            raise AyrshareProfileError(
                f"generateJWT failed ({resp.status_code}): {resp.text[:500]}")
        url = data.get("url")
        if not url:
            token = data.get("token")
            if not token:
                raise AyrshareProfileError(f"generateJWT returned no url/token: {data}")
            url = (f"https://profile.ayrshare.com/social-accounts"
                   f"?domain={self.config.ayrshare_domain}&jwt={token}")
        return url
