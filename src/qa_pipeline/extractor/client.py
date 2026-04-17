"""
extractor/client.py — Shared HTTP client with pagination, auth, and retry.

Wraps httpx with:
  • Bearer / Basic auth header injection
  • Jira-style cursor pagination  (startAt / maxResults / total)
  • Xray Cloud GraphQL pagination (page / limit)
  • tenacity retry on 429 / 5xx with exponential back-off
  • structured logging on every request
"""
from __future__ import annotations

import math
import time
from collections.abc import Generator, Iterator
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

log = structlog.get_logger(__name__)

# ── Retry predicate ────────────────────────────────────────────────────────────

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    return False


# ── Low-level client ───────────────────────────────────────────────────────────

class ApiClient:
    """
    Thin httpx wrapper.  Instantiate once per extractor run and close
    when done (use as a context manager or call :meth:`close`).

    Parameters
    ----------
    base_url:
        Root URL, e.g. ``https://yourinstance.atlassian.net``
    auth_token:
        Raw token string.  If it starts with ``Basic `` or ``Bearer ``
        the prefix is preserved; otherwise ``Bearer`` is prepended.
    retry_max:
        Maximum retry attempts on transient errors (default 5).
    backoff_base_ms:
        Base back-off in milliseconds for the first retry (default 1000).
    timeout:
        Request timeout in seconds (default 30).
    """

    def __init__(
        self,
        base_url: str,
        auth_token: str,
        retry_max: int = 5,
        backoff_base_ms: int = 1000,
        timeout: float = 30.0,
        http_proxy: str | None = None,
        https_proxy: str | None = None,
        ssl_ca_bundle: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._retry_max = retry_max
        self._backoff_base_ms = backoff_base_ms

        # Jira and Xray Server both use HTTP Basic auth.
        # Prefix with "Basic" unless the caller already supplied "Basic"/"Bearer".
        auth_header = (
            auth_token
            if auth_token.startswith(("Basic ", "Bearer "))
            else f"Basic {auth_token}"
        )

        mounts: dict[str, httpx.HTTPTransport] = {}
        if http_proxy:
            mounts["http://"] = httpx.HTTPTransport(proxy=http_proxy)
        if https_proxy:
            mounts["https://"] = httpx.HTTPTransport(proxy=https_proxy)

        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": auth_header,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            verify=ssl_ca_bundle or True,
            **({"mounts": mounts} if mounts else {}),
        )

    # ── Context manager ────────────────────────────────────────────────────────

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ── Core request ──────────────────────────────────────────────────────────

    def get(self, path: str, **params: Any) -> Any:
        """
        GET *path* with optional query *params*.
        Retries on 429/5xx up to retry_max times.
        Returns parsed JSON.
        """
        return self._get_with_retry(path, params)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        """POST *path* with JSON *body*. Returns parsed JSON."""
        return self._post_with_retry(path, body)

    # ── Pagination helpers ─────────────────────────────────────────────────────

    def paginate_jira(
        self,
        path: str,
        results_key: str = "issues",
        page_size: int = 100,
        **extra_params: Any,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages from a Jira REST endpoint using GET with
        ``startAt`` / ``maxResults`` / ``total`` pagination.
        """
        start_at = 0
        total: int | None = None

        while True:
            params = {"startAt": start_at, "maxResults": page_size, **extra_params}
            data = self.get(path, **params)

            page: list[dict[str, Any]] = data.get(results_key, [])
            if total is None:
                total = data.get("total", len(page))

            log.debug(
                "client.jira_page",
                path=path,
                start_at=start_at,
                page_len=len(page),
                total=total,
            )

            if not page:
                break

            yield page

            start_at += len(page)
            if start_at >= total:
                break

    def paginate_jira_post(
        self,
        path: str,
        body: dict[str, Any],
        results_key: str = "issues",
        page_size: int = 100,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages from POST /rest/api/3/search/jql (Jira Cloud).

        Uses cursor-based pagination via ``nextPageToken`` in the response.
        *body* contains the fixed fields (jql, fields, expand, etc.);
        ``maxResults`` and ``nextPageToken`` are managed automatically.
        """
        next_page_token: str | None = None

        while True:
            request_body = {**body, "maxResults": page_size}
            if next_page_token:
                request_body["nextPageToken"] = next_page_token

            data = self.post(path, request_body)
            page: list[dict[str, Any]] = data.get(results_key, [])

            log.debug(
                "client.jira_post_page",
                path=path,
                page_len=len(page),
                has_next=bool(data.get("nextPageToken")),
            )

            if not page:
                break

            yield page

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

    def paginate_xray_server(
        self,
        path: str,
        page_size: int = 100,
        **extra_params: Any,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages from Xray Server/DC endpoints.
        Xray Server uses ``page`` (1-based) and ``limit`` parameters;
        the response is a list (not a wrapper object).
        """
        page = 1

        while True:
            params = {"page": page, "limit": page_size, **extra_params}
            data = self.get(path, **params)

            # Some Xray Server endpoints return a list directly
            items: list[dict[str, Any]] = data if isinstance(data, list) else data.get("results", [])

            log.debug(
                "client.xray_server_page",
                path=path,
                page=page,
                page_len=len(items),
            )

            if not items:
                break

            yield items

            if len(items) < page_size:
                break  # last page

            page += 1

    def paginate_xray_cloud_graphql(
        self,
        query: str,
        variables: dict[str, Any],
        results_path: list[str],
        page_size: int = 100,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Yield pages from the Xray Cloud GraphQL endpoint.

        *results_path* is a list of keys to drill into the response,
        e.g. ``["getTestExecutions", "results"]``.
        *variables* must include any query-specific filters; ``limit``
        and ``start`` are injected automatically.
        """
        start = 0

        while True:
            vars_page = {**variables, "limit": page_size, "start": start}
            data = self.post("/graphql", {"query": query, "variables": vars_page})

            # drill into {"data": {"getTestExecutions": {"results": [...], "total": N}}}
            node: Any = data.get("data", {})
            for key in results_path[:-1]:
                node = node.get(key, {})
            items: list[dict[str, Any]] = node.get(results_path[-1], [])
            total: int = node.get("total", len(items))

            log.debug(
                "client.xray_cloud_page",
                results_path=results_path,
                start=start,
                page_len=len(items),
                total=total,
            )

            if not items:
                break

            yield items

            start += len(items)
            if start >= total:
                break

    # ── Internal retry wrappers ────────────────────────────────────────────────

    def _get_with_retry(self, path: str, params: dict[str, Any]) -> Any:
        attempt = 0
        backoff_s = self._backoff_base_ms / 1000.0

        while True:
            try:
                resp = self._client.get(path, params=params)
                resp.raise_for_status()
                log.debug("client.get", path=path, status=resp.status_code)
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if not _is_retryable(exc) or attempt >= self._retry_max:
                    log.error("client.get_failed", path=path, status=exc.response.status_code)
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt >= self._retry_max:
                    log.error("client.get_timeout", path=path, error=str(exc))
                    raise

            attempt += 1
            log.warning("client.retrying", path=path, attempt=attempt, backoff_s=backoff_s)
            time.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 60.0)

    def _post_with_retry(self, path: str, body: dict[str, Any]) -> Any:
        attempt = 0
        backoff_s = self._backoff_base_ms / 1000.0

        while True:
            try:
                resp = self._client.post(path, json=body)
                resp.raise_for_status()
                log.debug("client.post", path=path, status=resp.status_code)
                return resp.json()
            except httpx.HTTPStatusError as exc:
                if not _is_retryable(exc) or attempt >= self._retry_max:
                    log.error("client.post_failed", path=path, status=exc.response.status_code)
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                if attempt >= self._retry_max:
                    log.error("client.post_timeout", path=path, error=str(exc))
                    raise

            attempt += 1
            log.warning("client.retrying_post", path=path, attempt=attempt, backoff_s=backoff_s)
            time.sleep(backoff_s)
            backoff_s = min(backoff_s * 2, 60.0)
