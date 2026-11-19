import hashlib
import json
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from .config import settings
from .domain import AgingPriorityPolicy, QueuePolicy
from .models import Audit, Counter, Inbox, Organization, Outbox, Service, Ticket, User, now
from .security import utc

ACTIVE = ("booked", "waiting", "serving")


def fail(message, code=409):
    raise HTTPException(code, message)


class QueueService:
    def __init__(self, db: Session, org_id: str, actor="customer", policy: QueuePolicy | None = None):
        self.db, self.org_id, self.actor = db, org_id, actor
        self.policy = policy or AgingPriorityPolicy()

    def lock(self):
        # A single organization mutex establishes a consistent order across all commands.
        # SQLite is for local/test use; BEGIN IMMEDIATE serializes writers there.
        if self.db.bind.dialect.name == "sqlite":
            self.db.execute(
                text("UPDATE organizations SET sequence = sequence WHERE id = :id"), {"id": self.org_id}
            )
        org = self.db.scalar(
            select(Organization)
            .where(Organization.id == self.org_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
        if not org:
            fail("Organization not found", 404)
        return org

    def get(self, model, identifier):
        obj = self.db.get(model, identifier)
        if not obj or obj.org_id != self.org_id:
            fail("Resource not found", 404)
        return obj

    def record(self, action, target, ticket=None):
        self.db.add(Audit(org_id=self.org_id, actor=self.actor, action=action, target=target))
        if ticket and ticket.contact:
            self.db.add(
                Outbox(
                    org_id=self.org_id,
                    kind=action,
                    payload={
                        "ticket_id": ticket.id,
                        "token": ticket.token,
                        "contact": ticket.contact,
                        "channel": ticket.channel,
                        "status": ticket.status,
                        "counter_id": ticket.counter_id,
                    },
                )
            )

    def command(self, key: str, operation: str, payload: dict, callback):
        self.lock()
        identity = f"{self.org_id}:{operation}:{key}"
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        previous = self.db.get(Inbox, identity)
        if previous:
            if previous.fingerprint != fingerprint:
                fail("Idempotency key already used with different data")
            return previous.response
        result = callback()
        self.db.add(Inbox(id=identity, fingerprint=fingerprint, response=result))
        self.db.flush()
        return result

    def slots(self, service_id, day):
        service = self.get(Service, service_id)
        if not service.active:
            return []
        zone = ZoneInfo(settings.timezone)
        start = datetime.combine(day, time(9), zone)
        end = datetime.combine(day, time(17), zone)
        tickets = self.db.scalars(
            select(Ticket).where(
                Ticket.org_id == self.org_id,
                Ticket.service_id == service_id,
                Ticket.status.in_(ACTIVE),
                Ticket.slot >= start.astimezone(timezone.utc),
                Ticket.slot < end.astimezone(timezone.utc),
            )
        ).all()
        counts = {}
        for ticket in tickets:
            iso = utc(ticket.slot).isoformat()
            counts[iso] = counts.get(iso, 0) + 1
        result = []
        while start + timedelta(minutes=service.minutes) <= end:
            slot = start.astimezone(timezone.utc)
            if slot > now() and slot <= now() + timedelta(days=30):
                result.append(
                    {
                        "time": slot.isoformat(),
                        "remaining": max(0, service.capacity - counts.get(slot.isoformat(), 0)),
                    }
                )
            start += timedelta(minutes=service.minutes)
        return result

    def validate_slot(self, service_id, slot, excluding=None):
        slot = utc(slot)
        if not now() < slot <= now() + timedelta(days=30):
            fail("Choose a future slot within 30 days", 422)
        offered = self.slots(service_id, slot.astimezone(ZoneInfo(settings.timezone)).date())
        match = next((s for s in offered if s["time"] == slot.isoformat()), None)
        if not match:
            fail("Slot is outside service hours or misaligned", 422)
        same = excluding and excluding.slot and utc(excluding.slot) == slot
        if match["remaining"] <= 0 and not same:
            fail("This slot is full")

    def register(self, data, allow_priority=False):
        service = self.get(Service, data.service_id)
        if not service.active:
            fail("Service unavailable")
        if data.priority and not allow_priority:
            fail("Only reception may assign priority", 403)
        if data.slot:
            self.validate_slot(data.service_id, data.slot)
        org = self.db.get(Organization, self.org_id)
        org.sequence += 1
        ticket = Ticket(
            org_id=self.org_id,
            service_id=data.service_id,
            token=f"{'A' if data.slot else 'W'}-{org.sequence:04d}",
            name=data.name,
            contact=data.contact,
            channel=data.channel,
            source=data.source,
            priority=data.priority,
            status="booked" if data.slot else "waiting",
            slot=data.slot,
            checked_in=None if data.slot else now(),
        )
        self.db.add(ticket)
        self.db.flush()
        self.record("registered", ticket.id, ticket)
        return self.private_ticket(ticket)

    def by_secret(self, secret):
        ticket = self.db.scalar(select(Ticket).where(Ticket.secret == secret, Ticket.org_id == self.org_id))
        if not ticket:
            fail("Ticket not found", 404)
        return ticket

    def change(self, secret, action, slot=None):
        ticket = self.by_secret(secret)
        if action == "check-in":
            if ticket.status == "waiting":
                return self.private_ticket(ticket)
            if ticket.status != "booked":
                fail("Only a booked appointment can check in")
            org = self.db.get(Organization, self.org_id)
            if now() < utc(ticket.slot) - timedelta(minutes=30):
                fail("Check in opens 30 minutes before your appointment")
            if now() > utc(ticket.slot) + timedelta(minutes=org.grace_minutes):
                fail("Check-in grace period has expired; contact reception")
            ticket.status, ticket.checked_in = "waiting", now()
        elif action == "cancel":
            if ticket.status not in ("booked", "waiting"):
                fail("Only booked or waiting tickets can be cancelled")
            ticket.status = "cancelled"
        elif action == "reschedule":
            if ticket.status != "booked":
                fail("Only appointments awaiting check-in can be rescheduled")
            self.validate_slot(ticket.service_id, slot, ticket)
            ticket.slot = slot
        self.record(action, ticket.id, ticket)
        self.db.flush()
        return self.private_ticket(ticket)

    def expire(self):
        org = self.db.get(Organization, self.org_id)
        overdue = self.db.scalars(
            select(Ticket).where(
                Ticket.org_id == self.org_id,
                Ticket.status == "booked",
                Ticket.slot < now() - timedelta(minutes=org.grace_minutes),
            )
        ).all()
        for ticket in overdue:
            ticket.status = "no_show"
            self.record("no_show", ticket.id, ticket)
        return len(overdue)

    def ordered(self, service_id):
        tickets = self.db.scalars(
            select(Ticket).where(
                Ticket.org_id == self.org_id, Ticket.service_id == service_id, Ticket.status == "waiting"
            )
        ).all()
        return self.policy.order(tickets, now(), self.db.get(Organization, self.org_id))

    def authorize_counter(self, counter, user):
        if user.role == "staff" and counter.staff_id != user.id:
            fail("Counter is assigned to another staff member", 403)

    def dispatch(self, counter_id, user):
        counter = self.get(Counter, counter_id)
        self.authorize_counter(counter, user)
        if not counter.active or not counter.staff_id or not self.get(User, counter.staff_id).active:
            fail("Counter needs an available staff member")
        if not self.get(Service, counter.service_id).active:
            fail("Service unavailable")
        if self.db.scalar(
            select(Ticket.id).where(Ticket.counter_id == counter.id, Ticket.status == "serving")
        ):
            fail("Complete the current customer first")
        queue = self.ordered(counter.service_id)
        if not queue:
            fail("No customers waiting")
        ticket = queue[0]
        ticket.status, ticket.counter_id, ticket.started = "serving", counter.id, now()
        self.record("called", ticket.id, ticket)
        for upcoming in queue[1:3]:
            self.record("turn_approaching", upcoming.id, upcoming)
        self.db.flush()
        return self.private_ticket(ticket)

    def complete(self, counter_id, user):
        counter = self.get(Counter, counter_id)
        self.authorize_counter(counter, user)
        ticket = self.db.scalar(
            select(Ticket).where(
                Ticket.counter_id == counter.id, Ticket.org_id == self.org_id, Ticket.status == "serving"
            )
        )
        if not ticket:
            fail("No active customer")
        ticket.status, ticket.finished = "completed", now()
        self.record("completed", ticket.id, ticket)
        self.db.flush()
        return self.private_ticket(ticket)

    def estimate(self, ticket):
        if ticket.status != "waiting":
            return {"position": None, "eta_minutes": None}
        return self.estimates(ticket.service_id).get(ticket.id, {"position": None, "eta_minutes": None})

    def estimates(self, service_id):
        queue = self.ordered(service_id)
        counters = self.db.scalars(
            select(Counter)
            .join(User, Counter.staff_id == User.id)
            .where(
                Counter.org_id == self.org_id,
                Counter.service_id == service_id,
                Counter.active.is_(True),
                User.active.is_(True),
            )
        ).all()
        if not counters:
            return {t.id: {"position": i + 1, "eta_minutes": None} for i, t in enumerate(queue)}
        recent = self.db.scalars(
            select(Ticket)
            .where(
                Ticket.service_id == service_id,
                Ticket.org_id == self.org_id,
                Ticket.status == "completed",
            )
            .order_by(Ticket.finished.desc())
            .limit(30)
        ).all()
        mean = (
            sum(max(1, (utc(t.finished) - utc(t.started)).total_seconds() / 60) for t in recent) / len(recent)
            if recent
            else self.get(Service, service_id).minutes
        )
        loads = []
        for counter in counters:
            serving = self.db.scalar(
                select(Ticket).where(Ticket.counter_id == counter.id, Ticket.status == "serving")
            )
            loads.append(max(1, mean - (now() - utc(serving.started)).total_seconds() / 60) if serving else 0)
        import math

        result = {}
        for position, ticket in enumerate(queue, start=1):
            index = min(range(len(loads)), key=loads.__getitem__)
            wait = loads[index]
            loads[index] += mean
            result[ticket.id] = {"position": position, "eta_minutes": math.ceil(wait)}
        return result

    def private_ticket(self, ticket, estimates=None):
        return {
            "id": ticket.id,
            "secret": ticket.secret,
            "token": ticket.token,
            "name": ticket.name,
            "service_id": ticket.service_id,
            "service_name": self.service_name(ticket.service_id),
            "status": ticket.status,
            "slot": utc(ticket.slot).isoformat() if ticket.slot else None,
            "counter_id": ticket.counter_id,
            "priority": ticket.priority,
            **(
                self.estimate(ticket)
                if estimates is None
                else estimates.get(ticket.id, {"position": None, "eta_minutes": None})
            ),
        }

    def board(self):
        tickets = self.db.scalars(
            select(Ticket).where(Ticket.org_id == self.org_id, Ticket.status.in_(("waiting", "serving")))
        ).all()
        counters = self.counter_summaries(tickets)
        estimates = {}
        for service_id in {t.service_id for t in tickets if t.status == "waiting"}:
            estimates.update(self.estimates(service_id))
        return {
            "organization": self.db.get(Organization, self.org_id).name,
            "tickets": [
                {
                    "token": t.token,
                    "status": t.status,
                    "service_id": t.service_id,
                    "service_name": self.service_name(t.service_id),
                    "counter_id": t.counter_id,
                    **estimates.get(t.id, {"position": None, "eta_minutes": None}),
                }
                for t in tickets
            ],
            "counters": counters,
        }

    def service_name(self, service_id):
        if not hasattr(self, "_service_names"):
            self._service_names = dict(
                self.db.execute(select(Service.id, Service.name).where(Service.org_id == self.org_id)).all()
            )
        return self._service_names.get(service_id, "Service unavailable")

    def counter_summaries(self, tickets=None):
        """Public-safe counter state. Waiting counts belong to a shared service queue."""
        if tickets is None:
            tickets = self.db.scalars(
                select(Ticket).where(Ticket.org_id == self.org_id, Ticket.status.in_(("waiting", "serving")))
            ).all()
        counters = self.db.scalars(
            select(Counter).where(Counter.org_id == self.org_id).order_by(Counter.name, Counter.id)
        ).all()
        services = {s.id: s for s in self.db.scalars(select(Service).where(Service.org_id == self.org_id))}
        available_staff = set(
            self.db.scalars(select(User.id).where(User.org_id == self.org_id, User.active.is_(True)))
        )
        waiting = {}
        serving = {}
        for ticket in tickets:
            if ticket.status == "waiting":
                waiting[ticket.service_id] = waiting.get(ticket.service_id, 0) + 1
            elif ticket.status == "serving":
                serving[ticket.counter_id] = ticket.token
        result = []
        for counter in counters:
            service = services[counter.service_id]
            staffed = counter.staff_id in available_staff
            availability = (
                "paused"
                if not counter.active
                else "unstaffed"
                if not staffed
                else "service_unavailable"
                if not service.active
                else "serving"
                if counter.id in serving
                else "available"
            )
            result.append(
                {
                    "id": counter.id,
                    "name": counter.name,
                    "service_id": counter.service_id,
                    "service_name": service.name,
                    "service_active": service.active,
                    "active": counter.active,
                    "staffed": staffed,
                    "availability": availability,
                    "serving_token": serving.get(counter.id),
                    "waiting_count": waiting.get(counter.service_id, 0),
                }
            )
        return result
