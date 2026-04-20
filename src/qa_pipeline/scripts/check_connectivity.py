"""
scripts/check_connectivity.py — Verify Jira Cloud + Xray Cloud connectivity.

Tests, in order:
  1. Jira Cloud auth  — GET /rest/api/3/myself
  2. Xray Cloud auth  — POST /api/v2/authenticate (client_id + client_secret)
  3. Xray Cloud GraphQL — introspection ping to confirm the JWT works

Usage:
    qa-check-connectivity
    python -m qa_pipeline.scripts.check_connectivity
"""
from __future__ import annotations

import sys

import httpx
import structlog

from qa_pipeline.extractor.xray import _XRAY_AUTH_URL, _jwt_expires_at
from qa_pipeline.settings import PipelineSettings

log = structlog.get_logger(__name__)

_XRAY_GQL_URL = "https://xray.cloud.getxray.app/api/v2/graphql"
_GQL_PING = "{ __typename }"


def _check_jira(settings: PipelineSettings) -> bool:
    url = f"{str(settings.jira_base_url).rstrip('/')}/rest/api/3/myself"
    auth = f"Basic {settings.jira_auth_token.get_secret_value()}"
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": auth, "Accept": "application/json"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
        identity = data.get("displayName") or data.get("emailAddress") or data.get("accountId", "?")
        print(f"  [PASS] Jira Cloud authenticated as: {identity}")
        return True
    except httpx.HTTPStatusError as exc:
        print(f"  [FAIL] Jira Cloud HTTP {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] Jira Cloud: {exc}")
    return False


def _check_xray_auth(settings: PipelineSettings) -> str | None:
    if not settings.xray_client_id or not settings.xray_client_secret:
        print("  [FAIL] Xray Cloud: XRAY_CLIENT_ID or XRAY_CLIENT_SECRET not set")
        return None
    try:
        resp = httpx.post(
            _XRAY_AUTH_URL,
            json={
                "client_id": settings.xray_client_id.get_secret_value(),
                "client_secret": settings.xray_client_secret.get_secret_value(),
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        token: str = resp.json()
        if not isinstance(token, str) or not token:
            print(f"  [FAIL] Xray Cloud auth: unexpected response body: {token!r}")
            return None
        exp = _jwt_expires_at(token)
        import time
        ttl_h = (exp - time.time()) / 3600 if exp else 0
        print(f"  [PASS] Xray Cloud auth: JWT obtained, expires in {ttl_h:.1f}h")
        return token
    except httpx.HTTPStatusError as exc:
        print(f"  [FAIL] Xray Cloud auth HTTP {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] Xray Cloud auth: {exc}")
    return None


def _check_xray_graphql(token: str) -> bool:
    try:
        resp = httpx.post(
            _XRAY_GQL_URL,
            json={"query": _GQL_PING},
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            print(f"  [FAIL] Xray Cloud GraphQL errors: {data['errors']}")
            return False
        print("  [PASS] Xray Cloud GraphQL: reachable and responding")
        return True
    except httpx.HTTPStatusError as exc:
        print(f"  [FAIL] Xray Cloud GraphQL HTTP {exc.response.status_code}: {exc.response.text[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [FAIL] Xray Cloud GraphQL: {exc}")
    return False


def main() -> None:
    settings = PipelineSettings()
    results: list[bool] = []

    print("--- Jira Cloud ---")
    results.append(_check_jira(settings))

    print("--- Xray Cloud authentication ---")
    token = _check_xray_auth(settings)
    results.append(token is not None)

    if token:
        print("--- Xray Cloud GraphQL ---")
        results.append(_check_xray_graphql(token))

    print()
    if all(results):
        print("All connectivity checks passed.")
    else:
        print("One or more connectivity checks failed. Check credentials and network.")
        sys.exit(1)


if __name__ == "__main__":
    main()
