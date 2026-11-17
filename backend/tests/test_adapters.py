from unittest.mock import patch
import pytest
from app.config import Settings, settings
from app.models import Outbox
from app.worker import ConfiguredSender


@pytest.fixture
def event():
    return Outbox(
        id="evt-123",
        org_id="main",
        kind="called",
        payload={
            "token": "W-1",
            "contact": "visitor@example.com",
            "channel": "email",
            "status": "serving",
            "counter_id": "c1",
        },
    )


def test_smtp_uses_tls_and_deterministic_message_id(monkeypatch, event):
    monkeypatch.setattr(settings, "notification_mode", "smtp")
    monkeypatch.setattr(settings, "smtp_user", "test-user")
    monkeypatch.setattr(settings, "smtp_password", "test-secret")
    with patch("app.worker.smtplib.SMTP") as smtp:
        ConfiguredSender().send(event)
        conn = smtp.return_value.__enter__.return_value
        conn.starttls.assert_called_once()
        conn.login.assert_called_once_with("test-user", "test-secret")
        assert conn.send_message.call_args.args[0]["Message-ID"] == "<evt-123@queuepilot>"


def test_webhook_passes_deduplication_key(monkeypatch, event):
    monkeypatch.setattr(settings, "notification_mode", "webhook")
    monkeypatch.setattr(settings, "notification_webhook_url", "https://gateway.example/send")
    event.payload = {**event.payload, "channel": "whatsapp", "contact": "+919876543210"}
    with patch("app.worker.httpx.post") as post:
        ConfiguredSender().send(event)
        assert post.call_args.kwargs["headers"]["Idempotency-Key"] == "evt-123"
        assert post.call_args.kwargs["json"]["channel"] == "whatsapp"
        post.return_value.raise_for_status.assert_called_once()


def test_unsupported_channel_fails_instead_of_claiming_delivery(monkeypatch, event):
    monkeypatch.setattr(settings, "notification_mode", "smtp")
    event.payload = {**event.payload, "channel": "sms"}
    with pytest.raises(ValueError):
        ConfiguredSender().send(event)


@pytest.mark.parametrize("channel", ["sms", "whatsapp"])
def test_direct_twilio_adapter(monkeypatch, event, channel):
    import json

    monkeypatch.setattr(settings, "notification_mode", "providers")
    monkeypatch.setattr(settings, "twilio_account_sid", "AC" + "a" * 32)
    monkeypatch.setattr(settings, "twilio_auth_token", "test-only-token")
    monkeypatch.setattr(settings, "twilio_sms_from", "+15551234567")
    monkeypatch.setattr(settings, "twilio_whatsapp_from", "+15551234567")
    monkeypatch.setattr(settings, "twilio_whatsapp_content_sid", "HX" + "b" * 32)
    event.payload = {**event.payload, "channel": channel, "contact": "+919876543210"}
    with patch("app.worker.httpx.post") as post:
        ConfiguredSender().send(event)
        args = post.call_args.kwargs
        assert args["auth"] == ("AC" + "a" * 32, "test-only-token")
        if channel == "whatsapp":
            assert args["data"]["To"] == "whatsapp:+919876543210"
            assert args["data"]["ContentSid"] == "HX" + "b" * 32
            assert json.loads(args["data"]["ContentVariables"])["1"] == "W-1"
        else:
            assert args["data"]["To"] == "+919876543210"
            assert "W-1" in args["data"]["Body"]


def test_twilio_fails_closed_without_credentials(monkeypatch, event):
    monkeypatch.setattr(settings, "notification_mode", "providers")
    monkeypatch.setattr(settings, "twilio_account_sid", "")
    event.payload = {**event.payload, "channel": "sms", "contact": "+919876543210"}
    with pytest.raises(ValueError):
        ConfiguredSender().send(event)


def test_properties_file_and_environment_precedence(tmp_path, monkeypatch):
    path = tmp_path / "config.properties"
    path.write_text(
        'admin_password=long-test-password\norganization_name=From file\ncors_origins=["https://example.com"]\n'
    )
    monkeypatch.setenv("ORGANIZATION_NAME", "From environment")
    config = Settings(_env_file=path)
    assert config.organization_name == "From environment"
    assert config.admin_password == "long-test-password"
    assert config.cors_origins == ["https://example.com"]


def test_websocket_snapshot_and_origin_guard(env, monkeypatch):
    client, factory = env
    monkeypatch.setattr("app.main.SessionLocal", factory)
    with client.websocket_connect("/api/ws/board", headers={"origin": "http://localhost:5173"}) as ws:
        snapshot = ws.receive_json()
        assert snapshot["organization"] == "Test branch"
        assert snapshot["tickets"] == []
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws/board", headers={"origin": "https://evil.example"}):
            pass
