"""
models/extractor.py — Pydantic models for the Extraction layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ExtractorConfig(BaseModel):
    jira_base_url: str
    xray_base_url: str
    auth_token: str                            # base64 email:api_token or Bearer
    xray_variant: Literal["server", "cloud"] = "server"
    project_keys: list[str] = []
    max_results_per_page: int = 100
    rate_limit_retry_max: int = 5
    rate_limit_backoff_base_ms: int = 1000
    http_proxy: str | None = None              # e.g. http://proxy.corp.com:8080
    https_proxy: str | None = None             # e.g. http://proxy.corp.com:8080
    ssl_ca_bundle: str | None = None           # path to corporate CA bundle (.pem/.crt)


class ExtractorResult(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    run_type: Literal["delta", "full"]
    entity_type: str                           # "jira_issues" | "xray_test_runs" | …
    records_extracted: int = 0
    watermark_before: datetime | None = None
    watermark_after: datetime | None = None
    status: Literal["success", "failed"] = "success"
    error_message: str | None = None
