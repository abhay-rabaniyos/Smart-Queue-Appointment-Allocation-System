from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.models import Audit, Counter, Inbox, Outbox, Ticket, now
from .conftest import login, register


def command(client, path, body=None, key=None):
    return client.post(path, json=body, headers={"Idempotency-Key": key or uuid4().hex})


def next_slot(client):
    day = (now() + timedelta(days=1)).date().isoformat()
    return client.get(f"/api/services/svc/slots?day={day}").json()[0]["time"]


def test_walk_in_full_lifecycle_and_public_privacy(env):
    client, factory = env
    response = register(client, contact="visitor@example.com")
    assert response.status_code == 201, response.text
    ticket = response.json()
    assert ticket["token"] == "W-0001"
    assert ticket["position"] == 1 and ticket["eta_minutes"] == 0
    board = client.get("/api/board").json()
    assert not {"name", "contact", "secret", "id"} & board["tickets"][0].keys()
    login(client, "staff")
    called = command(client, "/api/counters/counter/call")
    assert called.status_code == 200, called.text
    assert called.json()["status"] == "serving"
    assert command(client, "/api/counters/counter/call").status_code == 409
    assert command(client, f"/api/tickets/{ticket['secret']}/cancel").status_code == 409
    assert command(client, "/api/counters/counter/complete").json()["status"] == "completed"
    assert command(client, "/api/counters/counter/complete").status_code == 409
    assert command(client, "/api/counters/counter/call").status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Outbox)) == 3
        assert db.scalar(select(func.count()).select_from(Audit)) == 3


def test_booking_capacity_cancellation_and_reuse(env):
    client, _ = env
    slot = next_slot(client)
    first = register(client, source="appointment", slot=slot).json()
    assert first["status"] == "booked"
    assert register(client, source="appointment", slot=slot).status_code == 201
    assert register(client, source="appointment", slot=slot).status_code == 409
    assert command(client, f"/api/tickets/{first['secret']}/cancel").status_code == 200
    assert register(client, source="appointment", slot=slot).status_code == 201


def test_reschedule_is_atomic_and_requires_booked(env):
    client, _ = env
    day = (now() + timedelta(days=1)).date().isoformat()
    slots = client.get(f"/api/services/svc/slots?day={day}").json()
    a, b = slots[0]["time"], slots[1]["time"]
    first = register(client, source="appointment", slot=a).json()
    for _ in range(2):
        assert register(client, source="appointment", slot=b).status_code == 201
    path = f"/api/tickets/{first['secret']}/reschedule"
    assert command(client, path, {"slot": b}).status_code == 409
    assert client.get(f"/api/tickets/{first['secret']}").json()["slot"] == a
    assert command(client, path, {"slot": a}).status_code == 200
    walk = register(client).json()
    assert command(client, f"/api/tickets/{walk['secret']}/reschedule", {"slot": b}).status_code == 409


def test_check_in_windows_and_repeated_check_in(env):
    client, factory = env
    ticket = register(client, source="appointment", slot=next_slot(client)).json()
    path = f"/api/tickets/{ticket['secret']}/check-in"
    assert command(client, path).status_code == 409
    with factory.begin() as db:
        db.get(Ticket, ticket["id"]).slot = now() + timedelta(minutes=10)
    assert command(client, path).json()["status"] == "waiting"
    assert command(client, path).json()["status"] == "waiting"
    other = register(client, source="appointment", slot=next_slot(client)).json()
    with factory.begin() as db:
        db.get(Ticket, other["id"]).slot = now() - timedelta(hours=1)
    assert command(client, f"/api/tickets/{other['secret']}/check-in").status_code == 409


def test_idempotency_inbox_conflict_and_rollback(env):
    client, factory = env
    key = uuid4().hex
    payload = {"service_id": "svc", "name": "Visitor"}
    first = command(client, "/api/tickets", payload, key)
    second = command(client, "/api/tickets", payload, key)
    assert first.json() == second.json()
    assert command(client, "/api/tickets", {**payload, "name": "Someone else"}, key).status_code == 409
    assert (
        command(client, "/api/tickets", {**payload, "service_id": "missing"}, uuid4().hex).status_code == 404
    )
    assert register(client).json()["token"] == "W-0002"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Inbox)) == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"name": " "},
        {"name": "x" * 101},
        {"priority": -1},
        {"priority": 3},
        {"contact": "invalid", "channel": "email"},
        {"contact": "1234", "channel": "sms"},
        {"contact": "+1x12345678", "channel": "whatsapp"},
        {"source": "appointment"},
        {"slot": "2026-01-01T10:00:00"},
        {"source": "appointment", "slot": "2020-01-01T10:00:00Z"},
        {"source": "appointment", "slot": "2099-01-01T10:00:00Z"},
        {"source": "invalid"},
        {"unexpected": True},
    ],
)
def test_invalid_registration(env, changes):
    client, _ = env
    assert register(client, **changes).status_code == 422


def test_priority_requires_reception_and_affects_order(env):
    client, _ = env
    standard = register(client).json()
    assert register(client, priority=2).status_code == 403
    login(client, "reception")
    urgent = command(
        client, "/api/reception/tickets", {"service_id": "svc", "name": "Priority Visitor", "priority": 1}
    ).json()
    assert client.get(f"/api/tickets/{standard['secret']}").json()["position"] == 2
    assert command(client, "/api/counters/counter/call").status_code == 403
    login(client, "staff")
    assert command(client, "/api/counters/counter/call").json()["id"] == urgent["id"]


def test_auth_roles_logout_and_csrf(env):
    client, _ = env
    assert client.get("/api/operations").status_code == 401
    assert command(client, "/api/admin/staff", {}).status_code == 401
    assert (
        client.post("/api/auth/login", json={"email": "admin@example.com", "password": "wrong"}).status_code
        == 401
    )
    login(client, "staff")
    assert command(client, "/api/admin/services", {"name": "Service"}).status_code == 403
    assert command(client, "/api/counters/other-counter/call").status_code == 404
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_org_isolation(env):
    client, _ = env
    assert register(client, service_id="other-svc").status_code == 404
    login(client, "other-admin")
    ops = client.get("/api/operations").json()
    assert {s["id"] for s in ops["services"]} == {"other-svc"}
    assert (
        client.put(
            "/api/admin/counters/counter", json={"name": "Intrusion", "service_id": "other-svc"}
        ).status_code
        == 404
    )


def test_no_counter_eta_and_qr(env):
    client, factory = env
    with factory.begin() as db:
        db.get(Counter, "counter").active = False
    ticket = register(client).json()
    assert ticket["eta_minutes"] is None
    qr = client.get(f"/api/tickets/{ticket['secret']}/qr")
    assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG")
    assert client.get("/api/tickets/missing").status_code == 404
    assert client.get("/api/tickets/missing/qr").status_code == 404


def test_counter_assignment_validation_and_busy_guard(env):
    client, _ = env
    login(client)
    payload = {"name": "New counter", "service_id": "svc", "staff_id": "staff"}
    assert command(client, "/api/admin/counters", payload).status_code == 409
    payload["staff_id"] = "reception"
    assert command(client, "/api/admin/counters", payload).status_code == 409
    payload["staff_id"] = "other-admin"
    assert command(client, "/api/admin/counters", payload).status_code == 404
    register(client)
    assert command(client, "/api/counters/counter/call").status_code == 200
    assert (
        client.put("/api/admin/counters/counter", json={"name": "Changed", "service_id": "svc"}).status_code
        == 409
    )
    assert client.put("/api/admin/staff/staff", json={"active": False}).status_code == 409
    assert client.put("/api/admin/staff/admin", json={"active": False}).status_code == 409


def test_admin_configuration_and_metrics(env):
    client, _ = env
    login(client)
    assert (
        command(client, "/api/admin/services", {"name": "Banking", "minutes": 5, "capacity": 3}).status_code
        == 201
    )
    assert (
        command(
            client,
            "/api/admin/staff",
            {
                "name": "New Staff",
                "email": "new@example.com",
                "password": "long-password-123",
                "role": "staff",
            },
        ).status_code
        == 201
    )
    assert (
        command(
            client,
            "/api/admin/staff",
            {
                "name": "Duplicate",
                "email": "new@example.com",
                "password": "long-password-123",
                "role": "staff",
            },
        ).status_code
        == 409
    )
    assert (
        client.put(
            "/api/admin/rules", json={"aging_minutes": 1, "priority_weight": 2, "grace_minutes": 5}
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/admin/rules", json={"aging_minutes": 0, "priority_weight": 2, "grace_minutes": 5}
        ).status_code
        == 422
    )
    register(client)
    assert (
        client.put(
            "/api/admin/services/svc", json={"name": "Changed", "minutes": 20, "capacity": 1}
        ).status_code
        == 409
    )
    assert client.get("/api/operations").json()["analytics"]["waiting"] == 1


def test_invalid_idempotency_and_slot_alignment(env):
    client, _ = env
    assert client.post("/api/tickets", json={"name": "Test", "service_id": "svc"}).status_code == 422
    slot = next_slot(client)
    from datetime import datetime

    bad = (datetime.fromisoformat(slot) + timedelta(minutes=1)).isoformat()
    assert register(client, source="appointment", slot=bad).status_code == 422


def test_login_throttling(env):
    client, _ = env
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"email": "admin@example.com", "password": "incorrect"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"email": "admin@example.com", "password": "test-password-123"}
        ).status_code
        == 429
    )
