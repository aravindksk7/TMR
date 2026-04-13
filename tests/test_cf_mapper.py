"""
tests/test_cf_mapper.py — Unit tests for CustomFieldMapper.
"""
from __future__ import annotations

import json

import pytest

from qa_pipeline.transformer.cf_mapper import CustomFieldMapper


@pytest.fixture
def mapper(tmp_path) -> CustomFieldMapper:
    """Mapper backed by a minimal field map written to a temp file."""
    mapping = {
        "mappings": [
            {
                "source_field_id": "customfield_10200",
                "logical_name":    "program_name",
                "target_table":    "dim_program",
                "target_column":   "program_name",
                "entity_type":     "jira_issue",
                "field_type":      "string",
            },
            {
                "source_field_id": "customfield_10100",
                "logical_name":    "test_type",
                "target_table":    "dim_test",
                "target_column":   "test_type_sk",
                "entity_type":     "xray_test",
                "field_type":      "select_value",
            },
            {
                "source_field_id": "customfield_10300",
                "logical_name":    "test_environments",
                "target_table":    "stg_xray_test_executions",
                "target_column":   "environments_json",
                "entity_type":     "xray_test_execution",
                "field_type":      "array",
            },
            {
                "source_field_id": "customfield_10102",
                "logical_name":    "manual_test_steps",
                "target_table":    "stg_xray_tests",
                "target_column":   "steps_json",
                "entity_type":     "xray_test",
                "field_type":      "json",
            },
            {
                "source_field_id": "customfield_10301",
                "logical_name":    "test_plan_key",
                "target_table":    "stg_xray_test_executions",
                "target_column":   "test_plan_key",
                "entity_type":     "xray_test_execution",
                "field_type":      "issue_key",
            },
        ]
    }
    map_file = tmp_path / "custom_field_map.json"
    map_file.write_text(json.dumps(mapping), encoding="utf-8")
    return CustomFieldMapper(str(map_file))


class TestExtract:
    def test_string_field_extracted(self, mapper):
        payload = {"customfield_10200": "Platform Alpha"}
        result = mapper.extract(payload, "jira_issue")
        assert result["program_name"] == "Platform Alpha"

    def test_string_field_missing_returns_none(self, mapper):
        result = mapper.extract({}, "jira_issue")
        assert result["program_name"] is None

    def test_entity_type_filter(self, mapper):
        # jira_issue mapping should not appear when extracting xray_test
        payload = {"customfield_10200": "Platform Alpha",
                   "customfield_10100": {"value": "Manual"}}
        result = mapper.extract(payload, "xray_test")
        assert "program_name" not in result
        assert result["test_type"] == "Manual"

    def test_select_value_extracted(self, mapper):
        payload = {"customfield_10100": {"value": "Cucumber", "id": "10002"}}
        result = mapper.extract(payload, "xray_test")
        assert result["test_type"] == "Cucumber"

    def test_select_value_none(self, mapper):
        result = mapper.extract({"customfield_10100": None}, "xray_test")
        assert result["test_type"] is None

    def test_array_field_serialised(self, mapper):
        payload = {
            "customfield_10300": [
                {"value": "Staging"},
                {"value": "Production"},
            ]
        }
        result = mapper.extract(payload, "xray_test_execution")
        parsed = json.loads(result["test_environments"])
        assert parsed == ["Staging", "Production"]

    def test_json_field_serialised(self, mapper):
        steps = [{"index": 1, "step": "Open", "result": "OK"}]
        payload = {"customfield_10102": steps}
        result = mapper.extract(payload, "xray_test")
        assert json.loads(result["manual_test_steps"]) == steps

    def test_issue_key_field(self, mapper):
        payload = {"customfield_10301": {"key": "PROJ-42", "id": "10042"}}
        result = mapper.extract(payload, "xray_test_execution")
        assert result["test_plan_key"] == "PROJ-42"

    def test_empty_string_returns_none(self, mapper):
        result = mapper.extract({"customfield_10200": ""}, "jira_issue")
        assert result["program_name"] is None


class TestMappingsFor:
    def test_returns_correct_count(self, mapper):
        jira_mappings = mapper.mappings_for("jira_issue")
        assert len(jira_mappings) == 1
        assert jira_mappings[0].logical_name == "program_name"

    def test_empty_for_unknown_entity(self, mapper):
        assert mapper.mappings_for("unknown_entity") == []


class TestInit:
    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            CustomFieldMapper(str(tmp_path / "nonexistent.json"))
