"""
alerting/alerter.py — Alert delivery (webhook + SMTP).

Sends failure notifications when pipeline jobs exceed error thresholds.
Supports two delivery channels that can be used independently or together:
  • Webhook (Teams / Slack / generic HTTP POST)
  • SMTP email
"""
from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass, field
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx
import structlog

log = structlog.get_logger(__name__)


@dataclass
class AlertConfig:
    webhook_url: str | None = None

    # SMTP settings
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_to: list[str] = field(default_factory=list)
    smtp_use_tls: bool = True


@dataclass
class AlertPayload:
    job_name: str
    status: str          # "failed" | "warning"
    message: str
    run_id: str | None = None
    records_extracted: int = 0
    rows_processed: int = 0
    error_detail: str | None = None


class Alerter:
    """
    Send alert notifications over webhook and/or SMTP.

    If both channels are configured, both are attempted.  A failure in
    one channel does not suppress delivery via the other.
    """

    def __init__(self, config: AlertConfig) -> None:
        self._cfg = config

    def send(self, payload: AlertPayload) -> None:
        """Dispatch the alert over all configured channels."""
        if self._cfg.webhook_url:
            self._send_webhook(payload)
        if self._cfg.smtp_host and self._cfg.smtp_to:
            self._send_email(payload)

    # ── Webhook ────────────────────────────────────────────────────────────────

    def _send_webhook(self, payload: AlertPayload) -> None:
        body = self._build_webhook_body(payload)
        try:
            resp = httpx.post(
                self._cfg.webhook_url,  # type: ignore[arg-type]
                json=body,
                timeout=10.0,
            )
            resp.raise_for_status()
            log.info("alerter.webhook_sent", job_name=payload.job_name, status=payload.status)
        except httpx.HTTPError as exc:
            log.error("alerter.webhook_failed", job_name=payload.job_name, error=str(exc))

    @staticmethod
    def _build_webhook_body(payload: AlertPayload) -> dict[str, Any]:
        """
        Build a Teams-compatible Adaptive Card payload.
        Generic enough to work as a plain JSON POST for Slack incoming webhooks
        or any system that accepts arbitrary JSON.
        """
        color = "attention" if payload.status == "failed" else "warning"
        summary = (
            f"Pipeline **{payload.job_name}** {payload.status.upper()}\n\n"
            f"Run ID: {payload.run_id or 'n/a'}\n"
            f"Records extracted: {payload.records_extracted}\n"
            f"Rows processed:    {payload.rows_processed}\n"
        )
        if payload.error_detail:
            summary += f"\n**Error:**\n```\n{payload.error_detail[:800]}\n```"

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": f"QA Pipeline Alert — {payload.job_name}",
                                "weight": "Bolder",
                                "size": "Medium",
                                "color": color,
                            },
                            {
                                "type": "TextBlock",
                                "text": summary,
                                "wrap": True,
                            },
                        ],
                    },
                }
            ],
        }

    # ── SMTP ───────────────────────────────────────────────────────────────────

    def _send_email(self, payload: AlertPayload) -> None:
        subject = f"[QA Pipeline] {payload.status.upper()} — {payload.job_name}"
        body_html = self._build_email_html(payload)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = self._cfg.smtp_from or self._cfg.smtp_user or ""
        msg["To"]      = ", ".join(self._cfg.smtp_to)
        msg.attach(MIMEText(body_html, "html"))

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self._cfg.smtp_host, self._cfg.smtp_port) as server:  # type: ignore[arg-type]
                if self._cfg.smtp_use_tls:
                    server.starttls(context=context)
                if self._cfg.smtp_user and self._cfg.smtp_password:
                    server.login(self._cfg.smtp_user, self._cfg.smtp_password)
                server.sendmail(
                    msg["From"],
                    self._cfg.smtp_to,
                    msg.as_string(),
                )
            log.info("alerter.email_sent", job_name=payload.job_name, to=self._cfg.smtp_to)
        except smtplib.SMTPException as exc:
            log.error("alerter.email_failed", job_name=payload.job_name, error=str(exc))

    @staticmethod
    def _build_email_html(payload: AlertPayload) -> str:
        color = "#d93025" if payload.status == "failed" else "#f9a825"
        error_block = ""
        if payload.error_detail:
            error_block = f"""
            <tr>
              <td style="padding:8px;background:#f5f5f5;">
                <pre style="margin:0;font-size:12px;white-space:pre-wrap;">{payload.error_detail[:1200]}</pre>
              </td>
            </tr>"""
        return f"""
        <html><body style="font-family:Arial,sans-serif;color:#333;">
          <h2 style="color:{color};">QA Pipeline Alert — {payload.job_name}</h2>
          <table cellpadding="4" style="border-collapse:collapse;width:100%;max-width:600px;">
            <tr><td style="font-weight:bold;width:180px;">Status</td>
                <td style="color:{color};">{payload.status.upper()}</td></tr>
            <tr><td style="font-weight:bold;">Run ID</td>
                <td>{payload.run_id or 'n/a'}</td></tr>
            <tr><td style="font-weight:bold;">Records extracted</td>
                <td>{payload.records_extracted}</td></tr>
            <tr><td style="font-weight:bold;">Rows processed</td>
                <td>{payload.rows_processed}</td></tr>
            <tr><td style="font-weight:bold;">Message</td>
                <td>{payload.message}</td></tr>
            {error_block}
          </table>
        </body></html>
        """
