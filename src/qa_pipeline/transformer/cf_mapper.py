"""
transformer/cf_mapper.py — Custom Field Mapper.

Loads config/custom_field_map.json and extracts mapped custom fields
from raw Jira/Xray API payloads into a flat {logical_name: value} dict.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

log = structlog.get_logger(__name__)


class FieldMapping(BaseModel):
    source_field_id: str
    logical_name: str = ""
    target_table: str
    target_column: str
    entity_type: str
    field_type: str = "string"


class CustomFieldMapper:
    """
    Reads the custom_field_map.json config and exposes :meth:`extract`
    to pull all mapped values from a single raw API payload.

    Field type coercion rules
    -------------------------
    string       — return raw value as str, or None
    select_value — return payload[field_id]["value"] (Jira select/radio)
    array        — return JSON-serialised list of {"value": ...} objects
    json         — return JSON-serialised raw value (already a dict/list)
    issue_key    — return payload[field_id]["key"] (Jira issue link object)
    """

    def __init__(self, map_path: str = "config/custom_field_map.json") -> None:
        path = Path(map_path)
        if not path.exists():
            raise FileNotFoundError(f"Custom field map not found: {path.resolve()}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._mappings: list[FieldMapping] = [
            FieldMapping(**m) for m in raw.get("mappings", [])
        ]
        log.info("cf_mapper.loaded", path=str(path), count=len(self._mappings))

    # ── Public API ─────────────────────────────────────────────────────────────

    def extract(
        self,
        payload: dict[str, Any],
        entity_type: str,
    ) -> dict[str, str | None]:
        """
        Return a flat dict of {logical_name: coerced_value} for every
        mapping whose entity_type matches *entity_type*.

        Missing or null fields are returned as None (not omitted).
        Unexpected coercion failures are logged as warnings and returned
        as None so the caller can decide whether to surface them.
        """
        result: dict[str, str | None] = {}
        for mapping in self._mappings:
            if mapping.entity_type != entity_type:
                continue
            raw_value = payload.get(mapping.source_field_id)
            try:
                coerced = self._coerce(raw_value, mapping)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "cf_mapper.coerce_error",
                    field_id=mapping.source_field_id,
                    logical_name=mapping.logical_name,
                    error=str(exc),
                )
                coerced = None
            result[mapping.logical_name] = coerced
        return result

    def mappings_for(self, entity_type: str) -> list[FieldMapping]:
        """Return all FieldMapping objects for a given entity_type."""
        return [m for m in self._mappings if m.entity_type == entity_type]

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _coerce(value: Any, mapping: FieldMapping) -> str | None:
        if value is None:
            return None

        field_type = mapping.field_type

        if field_type == "string":
            return str(value) if value != "" else None

        if field_type == "select_value":
            # Jira select/radio: {"value": "Manual", "id": "10001"}
            if isinstance(value, dict):
                return value.get("value")
            return str(value)

        if field_type == "array":
            # Jira multi-select: [{"value": "Staging"}, {"value": "Prod"}]
            if isinstance(value, list):
                return json.dumps([
                    item.get("value", item) if isinstance(item, dict) else item
                    for item in value
                ])
            return json.dumps([value])

        if field_type == "json":
            if isinstance(value, (dict, list)):
                return json.dumps(value, default=str)
            return str(value)

        if field_type == "issue_key":
            # Jira issue link: {"key": "PROJ-123", "id": "10042", ...}
            if isinstance(value, dict):
                return value.get("key")
            return str(value)

        # Fallback for unknown types — stringify
        log.warning(
            "cf_mapper.unknown_field_type",
            field_type=field_type,
            logical_name=mapping.logical_name,
        )
        return str(value)
