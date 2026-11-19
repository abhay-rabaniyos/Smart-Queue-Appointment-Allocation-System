import smtplib
from sqlalchemy import select
from app.models import Outbox, now
from app.worker import process_batch
from app.notification_errors import error_message
from .conftest import register, login


def test_recipient_failure_is_safe_visible_to_owner_and_staff_and_clears_on_recovery(env):
    client, factory = env
    first = register(client, contact="visitor@example.com").json()
    second = register(client).json()

    class Rejected:
        def send(self, event):
            raise smtplib.SMTPRecipientsRefused({"private@example.com": (550, b"SECRET PROVIDER DETAIL")})

    with factory.begin() as db:
        process_batch(db, Rejected())
        assert db.scalar(select(Outbox)).error == "SMTPRecipientsRefused"
    owned = client.get(f"/api/tickets/{first['secret']}").json()
    assert "recipient address" in owned["notification_error"]["message"]
    assert "SECRET" not in str(owned) and "private@example.com" not in str(owned)
    assert client.get(f"/api/tickets/{second['secret']}").json()["notification_error"] is None
    assert "notification_error" not in client.get("/api/board").json()["tickets"][0]
    login(client)
    assert "recipient address" in client.get("/api/operations").json()["outbox"][0]["error_message"]

    class Success:
        def send(self, event):
            pass

    with factory.begin() as db:
        db.scalar(select(Outbox)).available = now()
        db.flush()
        process_batch(db, Success())
    assert client.get(f"/api/tickets/{first['secret']}").json()["notification_error"] is None


def test_dead_letter_messages_do_not_promise_more_automatic_retries():
    message = error_message("TimeoutError", "dead")
    assert "will be retried" not in message
    assert "Automatic retries stopped" in message
    assert error_message(None) is None
    assert (
        error_message("UnrecognizedProviderException")
        == "Notification delivery failed. Ask an administrator to check the provider settings."
    )


def test_bad_email_is_rejected_before_queue_or_outbox_creation(env):
    client, factory = env
    assert register(client, contact="not-an-email").status_code == 422
    with factory() as db:
        assert db.scalar(select(Outbox)) is None
