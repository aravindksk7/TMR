"""
tests/test_staging_writer.py — Unit tests for StagingWriter.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, call, patch

import pytest

from qa_pipeline.models.staging import StagingRecord
from qa_pipeline.staging.writer import StagingWriter, _TABLE_MAP


@pytest.fixture
def run_id():
    return uuid.UUID("aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb")


def _make_record(run_id, source_key, entity_type, payload=None):
    return StagingRecord(
        run_id=run_id,
        source_key=source_key,
        entity_type=entity_type,
        raw_json=payload or {"key": source_key},
    )


class TestWriteBatch:
    def test_empty_batch_returns_zero(self, run_id):
        conn = MagicMock()
        writer = StagingWriter(conn)
        assert writer.write_batch([]) == 0
        conn.cursor.assert_not_called()

    def test_routes_to_correct_table(self, run_id):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        records = [_make_record(run_id, "QA-1", "jira_issue")]
        writer = StagingWriter(conn)
        count = writer.write_batch(records)

        assert count == 1
        sql_used = cursor.executemany.call_args[0][0]
        assert "stg_jira_issues" in sql_used

    def test_unknown_entity_type_skipped(self, run_id):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor

        # Bypass pydantic validation to simulate a record with an unknown type
        record = StagingRecord.model_construct(
            run_id=run_id,
            source_key="X-1",
            entity_type="unknown_type",
            raw_json="{}",
        )
        writer = StagingWriter(conn)
        count = writer.write_batch([record])

        assert count == 0
        cursor.executemany.assert_not_called()

    def test_mixed_entity_types_routed_correctly(self, run_id):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        records = [
            _make_record(run_id, "QA-1", "jira_issue"),
            _make_record(run_id, "QA-2", "jira_issue"),
            _make_record(run_id, "QA-3", "xray_test"),
        ]
        writer = StagingWriter(conn)
        count = writer.write_batch(records)

        assert count == 3
        # executemany called twice — once per table
        assert cursor.executemany.call_count == 2

    def test_batches_large_payload(self, run_id):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        records = [_make_record(run_id, f"QA-{i}", "jira_issue") for i in range(1200)]
        writer = StagingWriter(conn, batch_size=500)
        count = writer.write_batch(records)

        assert count == 1200
        # 1200 records / 500 batch_size = 3 executemany calls
        assert cursor.executemany.call_count == 3

    def test_context_manager_commits_on_success(self, run_id):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        records = [_make_record(run_id, "QA-1", "jira_issue")]
        with StagingWriter(conn) as writer:
            writer.write_batch(records)

        conn.commit.assert_called_once()
        conn.rollback.assert_not_called()

    def test_context_manager_rolls_back_on_exception(self, run_id):
        conn = MagicMock()

        with pytest.raises(ValueError):
            with StagingWriter(conn) as writer:
                raise ValueError("boom")

        conn.rollback.assert_called_once()
        conn.commit.assert_not_called()


class TestTableMap:
    def test_all_entity_types_mapped(self):
        from qa_pipeline.models.staging import EntityType
        import typing
        entity_types = typing.get_args(EntityType)
        for et in entity_types:
            assert et in _TABLE_MAP, f"No table mapping for entity_type '{et}'"
