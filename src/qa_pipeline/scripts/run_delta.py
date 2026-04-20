"""
scripts/run_delta.py — Incremental (delta) extraction + transformation.

Reads the watermark from pipeline_watermarks, extracts only records
updated since that timestamp, stages them, then runs an incremental
transformation.  Updates the watermark on success.

Invoked by:
  • CLI:       qa-delta  (pyproject.toml script)
  • Scheduler: delta_job  (scheduler/scheduler.py)
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone

import structlog

from qa_pipeline.alerting.alerter import AlertConfig, AlertPayload, Alerter
from qa_pipeline.db.connection import (
    build_connection,
    finish_run_log,
    get_watermark,
    set_watermark,
    start_run_log,
)
from qa_pipeline.extractor.jira import JiraExtractor
from qa_pipeline.extractor.xray import build_xray_extractor
from qa_pipeline.models.extractor import ExtractorConfig
from qa_pipeline.models.transformer import TransformerConfig
from qa_pipeline.settings import PipelineSettings
from qa_pipeline.staging.writer import StagingWriter
from qa_pipeline.transformer.transformer import Transformer

log = structlog.get_logger(__name__)

_WATERMARK_JOB = "delta_extractor"


def run_delta_job() -> None:
    """Entry point for the scheduler (no args)."""
    settings = PipelineSettings()
    _run(settings)


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="QA Pipeline — delta extraction")
    parser.add_argument("--since", default=None,
                        help="Override watermark with ISO datetime (e.g. 2024-01-01T00:00:00Z)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract and stage only; skip transformation")
    args = parser.parse_args()

    settings = PipelineSettings()
    watermark_override: datetime | None = None
    if args.since:
        watermark_override = datetime.fromisoformat(
            args.since.replace("Z", "+00:00")
        )
    _run(settings, watermark_override=watermark_override, dry_run=args.dry_run)


def _run(
    settings: PipelineSettings,
    watermark_override: datetime | None = None,
    dry_run: bool = False,
) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    run_id   = uuid.uuid4()
    run_start = datetime.now(tz=timezone.utc)
    log.info("delta.start", run_id=str(run_id))

    staging_dsn   = settings.staging_db_dsn.get_secret_value()
    reporting_dsn = settings.reporting_db_dsn.get_secret_value()

    staging_conn   = build_connection(staging_dsn)
    reporting_conn = build_connection(reporting_dsn)

    # Read watermark
    watermark: datetime | None = watermark_override or get_watermark(
        staging_conn, _WATERMARK_JOB
    )
    log.info("delta.watermark", watermark=watermark.isoformat() if watermark else None)

    db_run_id = start_run_log(
        staging_conn,
        job_name="delta",
        watermark_before=watermark,
    )

    total_extracted = 0
    total_upserted  = 0
    new_watermark:  datetime | None = None
    error_msg: str | None = None

    try:
        ext_config = ExtractorConfig(
            jira_base_url=str(settings.jira_base_url),
            xray_base_url=str(settings.xray_base_url),
            auth_token=settings.jira_auth_token.get_secret_value(),
            jira_api_version=settings.jira_api_version,
            xray_variant=settings.xray_variant,
            xray_client_id=settings.xray_client_id.get_secret_value() if settings.xray_client_id else None,
            xray_client_secret=settings.xray_client_secret.get_secret_value() if settings.xray_client_secret else None,
            project_keys=settings.project_keys,
            max_results_per_page=settings.max_results_per_page,
            rate_limit_retry_max=settings.rate_limit_retry_max,
            rate_limit_backoff_base_ms=settings.rate_limit_backoff_base_ms,
            http_proxy=settings.http_proxy,
            https_proxy=settings.https_proxy,
            no_proxy=settings.no_proxy,
            ssl_ca_bundle=settings.ssl_ca_bundle,
        )

        all_records = []

        # ── Jira delta extraction ──────────────────────────────────────────
        with JiraExtractor(ext_config, run_id) as jira_ext:
            records, result = jira_ext.extract(watermark=watermark)
            all_records.extend(records)
            total_extracted += result.records_extracted
            log.info("delta.jira_done", extracted=result.records_extracted,
                     status=result.status, watermark_after=str(result.watermark_after))

            if result.status == "failed":
                raise RuntimeError(result.error_message or "Jira delta extraction failed")

            if result.watermark_after:
                new_watermark = result.watermark_after

        # ── Xray delta extraction ──────────────────────────────────────────
        with build_xray_extractor(ext_config, run_id) as xray_ext:
            for project_key in settings.project_keys:
                recs, res = xray_ext.extract_tests(project_key, watermark=watermark)
                all_records.extend(recs)
                total_extracted += res.records_extracted

                recs, res = xray_ext.extract_test_executions(project_key, watermark=watermark)
                all_records.extend(recs)
                execution_records = recs
                total_extracted += res.records_extracted

                for exec_rec in execution_records:
                    run_recs, step_recs = xray_ext.extract_test_runs(exec_rec.source_key)
                    all_records.extend(run_recs)
                    all_records.extend(step_recs)
                    total_extracted += len(run_recs) + len(step_recs)

        log.info("delta.extraction_done", total_extracted=total_extracted)

        # ── Staging write ──────────────────────────────────────────────────
        with StagingWriter(staging_conn) as writer:
            staged = writer.write_batch(all_records)
        log.info("delta.staged", staged=staged)

        if dry_run:
            log.info("delta.dry_run_complete")
            finish_run_log(
                staging_conn, db_run_id,
                status="success",
                records_extracted=total_extracted,
                rows_processed=staged,
                rows_upserted=0,
                watermark_after=new_watermark,
            )
            return

        # ── Incremental transformation ─────────────────────────────────────
        tf_config = TransformerConfig(
            custom_field_map_path=settings.custom_field_map_path,
            mode="incremental",
            transformer_watermark=watermark,
        )
        transformer = Transformer(staging_conn, reporting_conn, tf_config)
        tf_result = transformer.run()

        total_upserted = tf_result.rows_upserted
        log.info("delta.transform_done",
                 rows_processed=tf_result.rows_processed,
                 rows_upserted=tf_result.rows_upserted,
                 warnings=len(tf_result.warnings),
                 status=tf_result.status)

        if tf_result.status == "failed":
            raise RuntimeError(tf_result.error_message or "Transformation failed")

        # Advance watermark only on full success
        effective_wm = new_watermark or run_start
        set_watermark(staging_conn, _WATERMARK_JOB, effective_wm)

        finish_run_log(
            staging_conn, db_run_id,
            status="success",
            records_extracted=total_extracted,
            rows_processed=tf_result.rows_processed,
            rows_upserted=tf_result.rows_upserted,
            watermark_after=effective_wm,
        )
        log.info("delta.complete", run_id=str(run_id), new_watermark=str(effective_wm))

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        log.error("delta.failed", error=error_msg)
        finish_run_log(
            staging_conn, db_run_id,
            status="failed",
            records_extracted=total_extracted,
            rows_upserted=total_upserted,
            watermark_after=new_watermark,
            error_message=error_msg,
            alert_sent=False,
        )
        _send_alert(settings, "delta", error_msg, total_extracted, total_upserted)
        sys.exit(1)
    finally:
        staging_conn.close()
        reporting_conn.close()


def _send_alert(
    settings: PipelineSettings,
    job_name: str,
    error_msg: str,
    extracted: int,
    upserted: int,
) -> None:
    try:
        smtp_to = [t.strip() for t in (settings.alert_smtp_to or "").split(",") if t.strip()]
        alert_cfg = AlertConfig(
            webhook_url=str(settings.alert_webhook_url) if settings.alert_webhook_url else None,
            smtp_host=settings.alert_smtp_host,
            smtp_port=settings.alert_smtp_port,
            smtp_user=settings.alert_smtp_user,
            smtp_password=settings.alert_smtp_password.get_secret_value() if settings.alert_smtp_password else None,
            smtp_from=settings.alert_smtp_from,
            smtp_to=smtp_to,
        )
        alerter = Alerter(alert_cfg)
        alerter.send(AlertPayload(
            job_name=job_name,
            status="failed",
            message=error_msg,
            records_extracted=extracted,
            rows_processed=upserted,
            error_detail=error_msg,
        ))
    except Exception as alert_exc:  # noqa: BLE001
        log.error("delta.alert_failed", error=str(alert_exc))


if __name__ == "__main__":
    main()
