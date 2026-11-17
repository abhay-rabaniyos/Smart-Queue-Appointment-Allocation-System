from datetime import timedelta
from types import SimpleNamespace
from sqlalchemy import select
from app.domain import AgingPriorityPolicy
from app.models import Audit, Organization, Outbox, Ticket, now
from app.services import QueueService
from app.worker import process_batch
from .conftest import register


def test_aging_prevents_starvation_and_ties_are_deterministic():
    at = now()
    old = SimpleNamespace(priority=0, checked_in=at - timedelta(minutes=1000), token="W-1")
    urgent = SimpleNamespace(priority=2, checked_in=at, token="W-2")
    rules = SimpleNamespace(priority_weight=30, aging_minutes=15)
    assert AgingPriorityPolicy().order([urgent, old], at, rules) == [old, urgent]
    same = SimpleNamespace(priority=0, checked_in=old.checked_in, token="W-0")
    assert AgingPriorityPolicy().order([old, same], at, rules) == [same, old]


def test_outbox_retry_backoff_dead_letter_and_recovery(env):
    client, factory = env
    register(client, contact="visitor@example.com")

    class Broken:
        def send(self, event):
            raise TimeoutError("must not leak provider response")

    for attempt in range(1, 6):
        with factory.begin() as db:
            event = db.scalar(select(Outbox))
            event.available = now() - timedelta(seconds=1)
            db.flush()
            assert process_batch(db, Broken()) == 1
            assert event.attempts == attempt
            assert event.error == "TimeoutError"
            assert event.state == ("dead" if attempt == 5 else "pending")
    from .conftest import login

    login(client)
    assert client.post(f"/api/admin/outbox/{event.id}/retry").status_code == 200

    class Success:
        def send(self, event):
            pass

    with factory.begin() as db:
        assert process_batch(db, Success()) == 1
        assert db.scalar(select(Outbox)).state == "simulated"
        assert process_batch(db, Success()) == 0


def test_transaction_rollback_removes_outbox_and_ticket(env):
    _, factory = env
    from app.schemas import Registration

    with factory() as db:
        service = QueueService(db, "main")
        service.lock()
        service.register(Registration(service_id="svc", name="Visitor", contact="v@example.com"))
        db.rollback()
    with factory() as db:
        assert db.scalar(select(Ticket)) is None
        assert db.scalar(select(Outbox)) is None
        assert db.get(Organization, "main").sequence == 0


def test_expire_no_show_releases_capacity_and_audits(env):
    client, factory = env
    from .test_workflows import next_slot

    ticket = register(client, source="appointment", slot=next_slot(client)).json()
    with factory.begin() as db:
        db.get(Ticket, ticket["id"]).slot = now() - timedelta(hours=1)
    with factory.begin() as db:
        service = QueueService(db, "main", "worker")
        service.lock()
        assert service.expire() == 1
        assert service.expire() == 0
    with factory() as db:
        assert db.get(Ticket, ticket["id"]).status == "no_show"
        assert db.scalar(select(Audit).where(Audit.action == "no_show")) is not None
