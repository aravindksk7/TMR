"""
scripts/run_full_load.py — Full-load entry point.

Performs a complete extraction of all Jira issues and Xray entities,
writes everything to staging, then runs a full_refresh transformation.

Invoked by:
  • CLI:       qa-full-load  (pyproject.toml script)
  • Scheduler: full_load_job  (scheduler/scheduler.py)
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone

import structlog

from qa_pipeline.alerting.alerter import AlertConfig, AlertPayload, Alerter
from qa_pipeline.db.connection import build_connection, finish_run_log, start_run_log
from qa_pipeline.extractor.jira import JiraExtractor
from qa_pipeline.extractor.xray import build_xray_extractor
from qa_pipeline.models.extractor import ExtractorConfig
from qa_pipeline.models.transformer import TransformerConfig
from qa_pipeline.settings import PipelineSettings
from qa_pipeline.staging.writer import StagingWriter
from qa_pipeline.transformer.transformer import Transformer

log = structlog.get_logger(__name__)


def run_full_load_job() -> None:
    """Entry point for the scheduler (no args)."""
    settings = PipelineSettings()
    _run(settings, mode="full_refresh")


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="QA Pipeline — full load")
    parser.add_argument("--dry-run", action="store_true",
                        help="Extract and stage only; skip transformation")
    args = parser.parse_args()

    settings = PipelineSettings()
    _run(settings, mode="full_refresh", dry_run=args.dry_run)


def _run(
    settings: PipelineSettings,
    mode: str = "full_refresh",
    dry_run: bool = False,
) -> None:
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

    run_id = uuid.uuid4()
    log.info("full_load.start", run_id=str(run_id), mode=mode)

    staging_dsn   = settings.staging_db_dsn.get_secret_value()
    reporting_dsn = settings.reporting_db_dsn.get_secret_value()

    staging_conn   = build_connection(staging_dsn)
    reporting_conn = build_connection(reporting_dsn)

    db_run_id = start_run_log(staging_conn, job_name="full_load")

    total_extracted = 0
    total_upserted  = 0
    error_msg: str | None = None

    try:
        ext_config = ExtractorConfig(
            jira_base_url=str(settings.jira_base_url),
            xray_base_url=str(settings.xray_base_url),
            auth_token=settings.jira_auth_token.get_secret_value(),
            jira_api_version=settings.jira_api_version,
            xray_variant=settings.xray_variant,
            project_keys=settings.project_keys,
            max_results_per_page=settings.max_results_per_page,
            rate_limit_retry_max=settings.rate_limit_retry_max,
            rate_limit_backoff_base_ms=settings.rate_limit_backoff_base_ms,
            http_proxy=settings.http_proxy,
            https_proxy=settings.https_proxy,
            ssl_ca_bundle=settings.ssl_ca_bundle,
        )

        all_records = []

        # ── Jira extraction ────────────────────────────────────────────────
        with JiraExtractor(ext_config, run_id) as jira_ext:
            records, result = jira_ext.extract(watermark=None)
            all_records.extend(records)
            total_extracted += result.records_extracted
            log.info("full_load.jira_done", extracted=result.records_extracted,
                     status=result.status)
            if result.status == "failed":
                raise RuntimeError(result.error_message or "Jira extraction failed")

        # ── Xray extraction ────────────────────────────────────────────────
        with build_xray_extractor(ext_config, run_id) as xray_ext:
            for project_key in settings.project_keys:
                # Tests
                recs, res = xray_ext.extract_tests(project_key, watermark=None)
                all_records.extend(recs)
                total_extracted += res.records_extracted

                # Test Executions
                recs, res = xray_ext.extract_test_executions(project_key, watermark=None)
                all_records.extend(recs)
                execution_records = recs
                total_extracted += res.records_extracted

                # Test Runs + Step Results (per execution)
                for exec_rec in execution_records:
                    run_recs, step_recs = xray_ext.extract_test_runs(exec_rec.source_key)
                    all_records.extend(run_recs)
                    all_records.extend(step_recs)
                    total_extracted += len(run_recs) + len(step_recs)

                # Test Sets
                recs, _ = xray_ext.extract_test_sets(project_key)
                all_records.extend(recs)

                # Preconditions
                recs, _ = xray_ext.extract_preconditions(project_key)
                all_records.extend(recs)

        log.info("full_load.extraction_done", total_extracted=total_extracted)

        # ── Staging write ──────────────────────────────────────────────────
        with StagingWriter(staging_conn) as writer:
            staged = writer.write_batch(all_records)
        log.info("full_load.staged", staged=staged)

        if dry_run:
            log.info("full_load.dry_run_complete")
            finish_run_log(
                staging_conn, db_run_id,
                status="success",
                records_extracted=total_extracted,
                rows_processed=staged,
                rows_upserted=0,
            )
            return

        # ── Transformation ─────────────────────────────────────────────────
        tf_config = TransformerConfig(
            custom_field_map_path=settings.custom_field_map_path,
            mode=mode,
            transformer_watermark=None,
        )
        transformer = Transformer(staging_conn, reporting_conn, tf_config)
        tf_result = transformer.run()

        total_upserted = tf_result.rows_upserted
        log.info("full_load.transform_done",
                 rows_processed=tf_result.rows_processed,
                 rows_upserted=tf_result.rows_upserted,
                 warnings=len(tf_result.warnings),
                 status=tf_result.status)

        if tf_result.status == "failed":
            raise RuntimeError(tf_result.error_message or "Transformation failed")

        finish_run_log(
            staging_conn, db_run_id,
            status="success",
            records_extracted=total_extracted,
            rows_processed=tf_result.rows_processed,
            rows_upserted=tf_result.rows_upserted,
        )
        log.info("full_load.complete", run_id=str(run_id))

    except Exception as exc:  # noqa: BLE001
        error_msg = str(exc)
        log.error("full_load.failed", error=error_msg)
        finish_run_log(
            staging_conn, db_run_id,
            status="failed",
            records_extracted=total_extracted,
            rows_upserted=total_upserted,
            error_message=error_msg,
            alert_sent=False,
        )
        _send_alert(settings, "full_load", error_msg, total_extracted, total_upserted)
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
        log.error("full_load.alert_failed", error=str(alert_exc))


if __name__ == "__main__":
    main()
