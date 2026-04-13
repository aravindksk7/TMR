"""
models/transformer.py — Pydantic models for the Transformation layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TransformerConfig(BaseModel):
    custom_field_map_path: str = "config/custom_field_map.json"
    mode: Literal["incremental", "full_refresh"] = "incremental"
    transformer_watermark: datetime | None = None


class Warning(BaseModel):
    source_key: str
    field_id: str
    message: str


class TransformerResult(BaseModel):
    run_id: UUID = Field(default_factory=uuid4)
    rows_processed: int = 0
    rows_upserted: int = 0
    warnings: list[Warning] = []
    status: Literal["success", "failed"] = "success"
    error_message: str | None = None
