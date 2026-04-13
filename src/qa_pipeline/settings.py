"""
settings.py — pipeline-wide configuration loaded from environment variables.

All secrets (tokens, DSNs) are read from the environment or a .env file.
Nothing is hardcoded. Import PipelineSettings() anywhere in the codebase.
"""
from __future__ import annotations

from pydantic import AnyHttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Jira / Xray ───────────────────────────────────────────────────────────
    jira_base_url: AnyHttpUrl
    xray_base_url: AnyHttpUrl
    jira_auth_token: SecretStr
    # "server" → REST /rest/raven/2.0/   "cloud" → GraphQL xray.cloud.getxray.app
    xray_variant: str = "server"
    # Comma-separated Jira project keys, e.g. "PROJ1,PROJ2"
    jira_project_keys: str = ""

    # ── SQL Server ────────────────────────────────────────────────────────────
    staging_db_dsn: SecretStr
    reporting_db_dsn: SecretStr
    # SQLAlchemy URL for APScheduler's SQLAlchemy job store
    scheduler_db_url: SecretStr

    # ── Extraction tuning ─────────────────────────────────────────────────────
    max_results_per_page: int = 100
    rate_limit_retry_max: int = 5
    rate_limit_backoff_base_ms: int = 1000

    # ── Transformer ───────────────────────────────────────────────────────────
    custom_field_map_path: str = "config/custom_field_map.json"

    # ── Scheduler cron expressions ────────────────────────────────────────────
    extractor_cron_hour: str = "*/4"   # delta run every 4 h
    full_load_cron_hour: int = 1       # full reload at 01:00 nightly

    # ── Alerting (all optional) ───────────────────────────────────────────────
    alert_webhook_url: AnyHttpUrl | None = None
    alert_smtp_host: str | None = None
    alert_smtp_port: int = 587
    alert_smtp_user: str | None = None
    alert_smtp_password: SecretStr | None = None
    alert_smtp_from: str | None = None
    alert_smtp_to: str | None = None   # comma-separated recipient list

    # ── Helpers ───────────────────────────────────────────────────────────────
    @property
    def project_keys(self) -> list[str]:
        """Return jira_project_keys as a list, stripping whitespace."""
        return [k.strip() for k in self.jira_project_keys.split(",") if k.strip()]
