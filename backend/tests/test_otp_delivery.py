"""
Tests for real OTP delivery (SMTP email + Termii/Twilio SMS) and console fallback.
Run with: pytest tests/test_otp_delivery.py -v
"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import pytest
from aiosmtpd.controller import Controller

from app.core.config import settings
from app.services import otp_service


class Capture:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope.content.decode("utf8", errors="replace"))
        return "250 OK"


@pytest.fixture
def smtp_server():
    handler = Capture()
    controller = Controller(handler, hostname="127.0.0.1", port=8025)
    controller.start()
    yield handler
    controller.stop()


@pytest.mark.asyncio
async def test_smtp_email_is_actually_sent(smtp_server, monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 8025)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")

    # local test server has no STARTTLS, so patch the sender to disable it
    import aiosmtplib
    real_send = aiosmtplib.send

    async def send_no_tls(msg, **kw):
        kw["start_tls"] = False
        return await real_send(msg, **kw)

    monkeypatch.setattr(aiosmtplib, "send", send_no_tls)

    await otp_service._deliver_email("user@example.com", "482913", "registration")
    assert len(smtp_server.messages) == 1
    assert "482913" in smtp_server.messages[0]
    assert "user@example.com" in smtp_server.messages[0]


@pytest.mark.asyncio
async def test_smtp_failure_falls_back_to_console(monkeypatch, caplog):
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "smtp")
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", 1)  # nothing listening
    with caplog.at_level("INFO", logger="zionhiltpay.otp"):
        await otp_service._deliver_email("user@example.com", "111222", "registration")
    assert "SMTP send" in caplog.text and "failed" in caplog.text
    assert "[EMAIL OTP]" in caplog.text  # fallback still surfaced the code


@pytest.mark.asyncio
async def test_termii_sms_payload(monkeypatch):
    monkeypatch.setattr(settings, "SMS_PROVIDER", "termii")
    monkeypatch.setattr(settings, "SMS_API_KEY", "test-key")
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"code": "ok", "message_id": "abc"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient
    monkeypatch.setattr(otp_service.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=transport, **kw))

    await otp_service._deliver_sms("+2348012345678", "654321", "registration")
    assert "termii.com" in seen["url"]
    assert "654321" in seen["body"] and "+2348012345678" in seen["body"]


@pytest.mark.asyncio
async def test_termii_rejection_falls_back(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SMS_PROVIDER", "termii")
    monkeypatch.setattr(settings, "SMS_API_KEY", "bad-key")
    transport = httpx.MockTransport(lambda r: httpx.Response(401, json={"message": "Invalid API key"}))
    real_client = httpx.AsyncClient
    monkeypatch.setattr(otp_service.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=transport, **kw))
    with caplog.at_level("INFO", logger="zionhiltpay.otp"):
        await otp_service._deliver_sms("+2348012345678", "999000", "registration")
    assert "failed" in caplog.text and "[SMS OTP]" in caplog.text


@pytest.mark.asyncio
async def test_production_never_logs_otp_code(monkeypatch, caplog):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "EMAIL_PROVIDER", "console")
    monkeypatch.setattr(settings, "SMS_PROVIDER", "console")
    with caplog.at_level("INFO", logger="zionhiltpay.otp"):
        await otp_service._deliver_email("user@example.com", "737373", "registration")
        await otp_service._deliver_sms("+2348012345678", "737373", "registration")
    assert "737373" not in caplog.text
