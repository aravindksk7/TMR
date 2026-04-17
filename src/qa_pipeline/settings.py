"""
settings.py — pipeline-wide configuration loaded from environment variables.

All secrets (tokens, DSNs) are read from the environment or a .env file.
Nothing is hardcoded. Import PipelineSettings() anywhere in the codebase.
"""
from __future__ import annotations

from pydantic import AliasChoices, AnyHttpUrl, Field, SecretStr
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
    # "2" for Jira Server/DC (on-premises), "3" for Jira Cloud
    jira_api_version: str = "2"
    # "server" → REST /rest/raven/2.0/   "cloud" → GraphQL xray.cloud.getxray.app
    xray_variant: str = "server"
    # Xray Cloud OAuth credentials (required when xray_variant=cloud)
    xray_client_id: str | None = None
    xray_client_secret: str | None = None
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

    # ── Proxy (all optional) ─────────────────────────────────────────────────
    http_proxy: str | None = None   # e.g. http://proxy.corp.com:8080
    https_proxy: str | None = None  # e.g. http://proxy.corp.com:8080
    no_proxy: str | None = None     # comma-separated hosts to bypass

    # ── SSL (optional — set to corporate CA bundle path in on-premises envs) ──
    # Accepts SSL_CERT_FILE or REQUESTS_CA_BUNDLE (whichever is set in .env)
    ssl_ca_bundle: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ssl_ca_bundle", "ssl_cert_file", "requests_ca_bundle"),
    )

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
