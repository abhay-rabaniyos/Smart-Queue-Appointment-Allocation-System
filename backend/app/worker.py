"""Durable at-least-once delivery. Provider adapters must deduplicate the event ID."""

import logging
import json
import re
import smtplib
import time
from datetime import timedelta
from email.message import EmailMessage
from typing import Protocol
import httpx
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Organization, Outbox, now
from .services import QueueService

logger = logging.getLogger(__name__)


class NotificationSender(Protocol):
    def send(self, event: Outbox) -> None: ...


class ConfiguredSender:
    def send(self, event):
        p = event.payload
        message = f"QueuePilot {p['token']}: {event.kind.replace('_', ' ')}. Status: {p['status']}."
        if settings.notification_mode == "console":
            logger.info("Simulated notification event=%s kind=%s", event.id, event.kind)
            return
        if settings.notification_mode in ("smtp", "providers") and p["channel"] == "email":
            mail = EmailMessage()
            mail["From"], mail["To"], mail["Subject"] = settings.smtp_from, p["contact"], "QueuePilot update"
            mail["Message-ID"] = f"<{event.id}@queuepilot>"
            mail.set_content(message)
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(mail)
            return
        if settings.notification_mode == "providers" and p["channel"] in ("sms", "whatsapp"):
            if (
                not re.fullmatch(r"AC[0-9a-fA-F]{32}", settings.twilio_account_sid)
                or not settings.twilio_auth_token
            ):
                raise ValueError("Twilio credentials are missing or invalid")
            whatsapp = p["channel"] == "whatsapp"
            sender = settings.twilio_whatsapp_from if whatsapp else settings.twilio_sms_from
            if not re.fullmatch(r"\+[0-9]{8,15}", sender):
                raise ValueError("Configure an international sender number")
            prefix = "whatsapp:" if whatsapp else ""
            data = {"To": prefix + p["contact"], "From": prefix + sender}
            if whatsapp:
                if not re.fullmatch(r"HX[0-9a-fA-F]{32}", settings.twilio_whatsapp_content_sid):
                    raise ValueError("Configure an approved WhatsApp content template")
                data.update(
                    {
                        "ContentSid": settings.twilio_whatsapp_content_sid,
                        "ContentVariables": json.dumps(
                            {"1": p["token"], "2": event.kind.replace("_", " "), "3": p["status"]}
                        ),
                    }
                )
            else:
                data["Body"] = message
            response = httpx.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
                auth=(settings.twilio_account_sid, settings.twilio_auth_token),
                data=data,
                timeout=10,
            )
            response.raise_for_status()
            return
        if settings.notification_mode == "webhook" and settings.notification_webhook_url.startswith(
            "https://"
        ):
            response = httpx.post(
                settings.notification_webhook_url,
                timeout=10,
                headers={
                    "Authorization": f"Bearer {settings.notification_webhook_token}",
                    "Idempotency-Key": event.id,
                },
                json={"event_id": event.id, "channel": p["channel"], "to": p["contact"], "message": message},
            )
            response.raise_for_status()
            return
        raise ValueError("Notification provider not configured for this channel")


def process_batch(db, sender: NotificationSender, limit=20):
    events = db.scalars(
        select(Outbox)
        .where(Outbox.state == "pending", Outbox.available <= now())
        .order_by(Outbox.created)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for event in events:
        event.attempts += 1
        try:
            sender.send(event)
            event.state, event.error = (
                ("simulated" if settings.notification_mode == "console" else "sent"),
                None,
            )
        except Exception as exc:
            # Never store provider responses, secrets, or customer contact data in error logs.
            event.error = type(exc).__name__
            event.state = "dead" if event.attempts >= 5 else "pending"
            event.available = now() + timedelta(seconds=min(3600, 2**event.attempts * 5))
    return len(events)


def run():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal.begin() as db:
                for org in db.scalars(select(Organization).order_by(Organization.id)):
                    service = QueueService(db, org.id, "worker")
                    service.lock()
                    service.expire()
            with SessionLocal.begin() as db:
                process_batch(db, ConfiguredSender())
        except Exception:
            logger.exception("Worker cycle failed")
        time.sleep(2)


if __name__ == "__main__":
    run()
