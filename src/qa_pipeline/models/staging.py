"""
models/staging.py — Pydantic models for the Staging layer.
"""
from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator

EntityType = Literal[
    "jira_issue",
    "jira_defect",
    "jira_version",
    "xray_test",
    "xray_test_run",
    "xray_test_execution",
    "xray_test_plan",
    "xray_test_step_result",
    "xray_test_set",
    "xray_precondition",
]


class StagingRecord(BaseModel):
    run_id: UUID
    source_key: str          # Jira issue key or Xray numeric/GUID ID
    entity_type: EntityType
    raw_json: str            # serialised JSON string

    @field_validator("raw_json", mode="before")
    @classmethod
    def serialise_dict(cls, v: object) -> str:
        """Accept dict payloads and serialise them automatically."""
        if isinstance(v, dict):
            return json.dumps(v, default=str)
        return str(v)
