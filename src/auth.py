"""
auth.py — Kalshi authentication.
"""

import requests
from .config import BASE_URL, REQUEST_TIMEOUT


class AuthError(Exception):
    pass


def login(email: str, password: str) -> str:
    """Authenticate with Kalshi and return a session token."""
    try:
        resp = requests.post(
            f"{BASE_URL}/login",
            json={"email": email, "password": password},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise AuthError(f"HTTP {e.response.status_code}: {e.response.text}") from e
    except requests.RequestException as e:
        raise AuthError(str(e)) from e

    token = resp.json().get("token")
    if not token:
        raise AuthError("No token in response — check credentials.")
    return token


def get_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
