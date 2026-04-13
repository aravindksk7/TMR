"""
tests/test_seed_dim_date.py — Unit tests for seed_dim_date logic.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from qa_pipeline.scripts.seed_dim_date import _build_row, seed


class TestBuildRow:
    def test_date_sk_format(self):
        row = _build_row(date(2024, 3, 15))
        assert row[0] == 20240315          # date_sk

    def test_full_date(self):
        d = date(2024, 6, 1)
        row = _build_row(d)
        assert row[1] == d

    def test_year_month_day(self):
        row = _build_row(date(2024, 11, 7))
        assert row[2] == 2024   # year
        assert row[4] == 11     # month
        assert row[7] == 7      # day_of_month (index 7; index 6 is week_of_year)

    def test_saturday_is_weekend(self):
        saturday = date(2024, 3, 16)   # Saturday
        row = _build_row(saturday)
        assert row[10] == 1    # is_weekend

    def test_monday_not_weekend(self):
        monday = date(2024, 3, 11)
        row = _build_row(monday)
        assert row[10] == 0    # is_weekend

    def test_quarter_q1(self):
        row = _build_row(date(2024, 2, 1))
        assert row[3] == 1     # quarter

    def test_quarter_q4(self):
        row = _build_row(date(2024, 11, 1))
        assert row[3] == 4     # quarter

    def test_month_name(self):
        row = _build_row(date(2024, 7, 4))
        assert row[5] == "July"

    def test_day_name_wednesday(self):
        # 2024-01-03 is a Wednesday
        row = _build_row(date(2024, 1, 3))
        assert row[9] == "Wednesday"

    def test_fiscal_equals_calendar_year(self):
        row = _build_row(date(2024, 5, 1))
        assert row[11] == 2024  # fiscal_year


class TestSeed:
    def test_seeds_correct_number_of_rows(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        n = seed(conn, date(2024, 1, 1), date(2024, 1, 10), batch_size=500)
        assert n == 10
        conn.commit.assert_called_once()

    def test_batches_correctly(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        # 10 rows, batch_size=3 → ceil(10/3) = 4 executemany calls
        seed(conn, date(2024, 1, 1), date(2024, 1, 10), batch_size=3)
        assert cursor.executemany.call_count == 4

    def test_single_day_range(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        n = seed(conn, date(2024, 6, 15), date(2024, 6, 15))
        assert n == 1

    def test_end_before_start_seeds_nothing(self):
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fast_executemany = False
        conn.cursor.return_value = cursor

        n = seed(conn, date(2024, 6, 15), date(2024, 6, 14))
        assert n == 0
        cursor.executemany.assert_not_called()
