"""Run against SQLite locally; TEST_DATABASE_URL enables PostgreSQL in CI."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Ticket
from app.schemas import Registration
from app.services import QueueService
from .test_workflows import next_slot


def test_concurrent_booking_cannot_oversell(env):
    client, factory = env
    slot = next_slot(client)

    def book(_):
        with factory() as db:
            service = QueueService(db, "main")
            data = Registration(service_id="svc", name="Concurrent Visitor", source="appointment", slot=slot)
            try:
                result = service.command(
                    uuid4().hex, "register", data.model_dump(mode="json"), lambda: service.register(data)
                )
                db.commit()
                return result["token"]
            except HTTPException as e:
                db.rollback()
                assert e.status_code == 409
                return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(book, range(10)))
    tokens = [r for r in results if r]
    assert len(tokens) == 2 and len(set(tokens)) == 2


def test_concurrent_retry_creates_one_ticket(env):
    _, factory = env
    key = uuid4().hex

    def create(_):
        with factory() as db:
            service = QueueService(db, "main")
            data = Registration(service_id="svc", name="One Visitor")
            result = service.command(
                key, "register", data.model_dump(mode="json"), lambda: service.register(data)
            )
            db.commit()
            return result["id"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(create, range(10)))
    assert len(set(results)) == 1
    with factory() as db:
        assert len(db.scalars(select(Ticket)).all()) == 1


def test_concurrent_dispatch_claims_once(env):
    _, factory = env
    from app.models import User

    with factory.begin() as db:
        service = QueueService(db, "main")
        service.lock()
        service.register(Registration(service_id="svc", name="One Visitor"))

    def dispatch(_):
        with factory() as db:
            service = QueueService(db, "main", "staff")
            try:
                # Simulate authentication having read from the session before command locking.
                user = db.get(User, "staff")
                result = service.command(
                    uuid4().hex, "call", {"counter": "counter"}, lambda: service.dispatch("counter", user)
                )
                db.commit()
                return result["id"]
            except HTTPException as e:
                db.rollback()
                assert e.status_code == 409
                return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(dispatch, range(6)))
    assert len([r for r in results if r]) == 1
