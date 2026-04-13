"""
tests/test_alerter.py — Unit tests for Alerter (webhook + SMTP).
"""
from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import httpx
import pytest
import respx

from qa_pipeline.alerting.alerter import AlertConfig, AlertPayload, Alerter


@pytest.fixture
def payload():
    return AlertPayload(
        job_name="delta",
        status="failed",
        message="DB connection timeout",
        run_id="abc-123",
        records_extracted=250,
        rows_processed=0,
        error_detail="pyodbc.OperationalError: [08S01] timeout",
    )


class TestWebhook:
    @respx.mock
    def test_sends_post_request(self, payload):
        route = respx.post("https://hooks.example.com/webhook").mock(
            return_value=httpx.Response(200, json={"ok": True})
        )
        cfg = AlertConfig(webhook_url="https://hooks.example.com/webhook")
        Alerter(cfg).send(payload)
        assert route.called

    @respx.mock
    def test_request_contains_job_name(self, payload):
        respx.post("https://hooks.example.com/webhook").mock(
            return_value=httpx.Response(200, json={})
        )
        cfg = AlertConfig(webhook_url="https://hooks.example.com/webhook")
        Alerter(cfg).send(payload)
        body = respx.calls.last.request.content.decode()
        assert "delta" in body

    @respx.mock
    def test_webhook_failure_does_not_raise(self, payload):
        respx.post("https://hooks.example.com/webhook").mock(
            return_value=httpx.Response(500, json={"error": "server error"})
        )
        cfg = AlertConfig(webhook_url="https://hooks.example.com/webhook")
        # Should log error but not propagate
        Alerter(cfg).send(payload)

    def test_no_webhook_url_skips_send(self, payload):
        cfg = AlertConfig(webhook_url=None)
        with patch("httpx.post") as mock_post:
            Alerter(cfg).send(payload)
        mock_post.assert_not_called()


class TestSmtp:
    def test_sends_email_when_configured(self, payload):
        cfg = AlertConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_user="user@example.com",
            smtp_password="secret",
            smtp_from="pipeline@example.com",
            smtp_to=["qa@example.com"],
        )
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_server = MagicMock()
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            Alerter(cfg).send(payload)
        mock_smtp_cls.assert_called_once_with("smtp.example.com", 587)

    def test_no_smtp_host_skips_email(self, payload):
        cfg = AlertConfig(smtp_host=None, smtp_to=["qa@example.com"])
        with patch("smtplib.SMTP") as mock_smtp:
            Alerter(cfg).send(payload)
        mock_smtp.assert_not_called()

    def test_no_smtp_to_skips_email(self, payload):
        cfg = AlertConfig(smtp_host="smtp.example.com", smtp_to=[])
        with patch("smtplib.SMTP") as mock_smtp:
            Alerter(cfg).send(payload)
        mock_smtp.assert_not_called()

    def test_smtp_failure_does_not_raise(self, payload):
        cfg = AlertConfig(
            smtp_host="smtp.example.com",
            smtp_to=["qa@example.com"],
        )
        with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("auth failed")):
            # Should log error but not propagate
            Alerter(cfg).send(payload)


class TestBothChannels:
    @respx.mock
    def test_both_channels_attempted(self, payload):
        webhook_route = respx.post("https://hooks.example.com/wh").mock(
            return_value=httpx.Response(200, json={})
        )
        cfg = AlertConfig(
            webhook_url="https://hooks.example.com/wh",
            smtp_host="smtp.example.com",
            smtp_to=["qa@example.com"],
        )
        with patch("smtplib.SMTP") as mock_smtp_cls:
            mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
            Alerter(cfg).send(payload)

        assert webhook_route.called
        mock_smtp_cls.assert_called_once()
