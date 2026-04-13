"""
scripts/seed_dim_date.py — Populate dim_date in Reporting_DB.

Generates one row per calendar day for the given range (default 2018-01-01
to 2030-12-31).  Safe to re-run: existing rows are skipped via MERGE.

Usage:
    qa-seed-dates                                    # default range from .env
    qa-seed-dates --start 2015-01-01 --end 2035-12-31
    python -m qa_pipeline.scripts.seed_dim_date --start 2015-01-01
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import pyodbc
import structlog

from qa_pipeline.db.connection import build_connection
from qa_pipeline.settings import PipelineSettings

log = structlog.get_logger(__name__)

_MERGE_DATE = """
MERGE dim_date AS tgt
USING (VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)) AS src
      (date_sk, full_date, year, quarter, month, month_name,
       week_of_year, day_of_month, day_of_week, day_name,
       is_weekend, fiscal_year, fiscal_quarter)
ON tgt.date_sk = src.date_sk
WHEN NOT MATCHED THEN
    INSERT (date_sk, full_date, year, quarter, month, month_name,
            week_of_year, day_of_month, day_of_week, day_name,
            is_weekend, fiscal_year, fiscal_quarter)
    VALUES (src.date_sk, src.full_date, src.year, src.quarter, src.month,
            src.month_name, src.week_of_year, src.day_of_month, src.day_of_week,
            src.day_name, src.is_weekend, src.fiscal_year, src.fiscal_quarter);
"""

_MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _build_row(d: date) -> tuple:
    iso_weekday    = d.isoweekday()        # 1=Mon … 7=Sun
    quarter        = (d.month - 1) // 3 + 1
    iso_week       = d.isocalendar()[1]
    is_weekend     = 1 if iso_weekday >= 6 else 0
    date_sk        = int(d.strftime("%Y%m%d"))
    fiscal_year    = d.year                # adjust cutover if fiscal ≠ calendar
    fiscal_quarter = quarter
    return (
        date_sk,
        d,
        d.year,
        quarter,
        d.month,
        _MONTH_NAMES[d.month],
        iso_week,
        d.day,
        iso_weekday,
        _DAY_NAMES[iso_weekday - 1],
        is_weekend,
        fiscal_year,
        fiscal_quarter,
    )


def seed(
    conn: pyodbc.Connection,
    start: date,
    end: date,
    batch_size: int = 500,
) -> int:
    """Insert/skip dim_date rows from *start* to *end* inclusive. Returns row count."""
    cursor = conn.cursor()
    cursor.fast_executemany = True
    total = 0
    batch: list[tuple] = []

    current = start
    while current <= end:
        batch.append(_build_row(current))
        current += timedelta(days=1)
        if len(batch) >= batch_size:
            cursor.executemany(_MERGE_DATE, batch)
            total += len(batch)
            batch = []

    if batch:
        cursor.executemany(_MERGE_DATE, batch)
        total += len(batch)

    conn.commit()
    log.info("seed_dim_date.done", start=str(start), end=str(end), rows=total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed dim_date table in Reporting_DB")
    parser.add_argument("--start", default="2018-01-01", help="Start date YYYY-MM-DD")
    parser.add_argument("--end",   default="2030-12-31", help="End date YYYY-MM-DD")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    end   = date.fromisoformat(args.end)

    settings = PipelineSettings()
    dsn = settings.reporting_db_dsn.get_secret_value()

    conn = build_connection(dsn)
    try:
        n = seed(conn, start, end)
    finally:
        conn.close()

    print(f"Seeded {n} rows into dim_date ({start} \u2192 {end})")


if __name__ == "__main__":
    main()
