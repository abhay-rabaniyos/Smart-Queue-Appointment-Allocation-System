from datetime import timedelta
from sqlalchemy import select
from app.models import Counter, Ticket, User, now
from .conftest import login, register
from .test_workflows import command


def test_automatic_allocation_uses_only_eligible_idle_counters(env):
    client, _ = env
    ticket = register(client).json()
    login(client)
    response = command(client, "/api/admin/dispatch")
    assert response.status_code == 200, response.text
    assert [t["id"] for t in response.json()["allocated"]] == [ticket["id"]]
    assert command(client, "/api/admin/dispatch").json()["allocated"] == []


def test_disabled_staff_and_paused_counter_cannot_dispatch(env):
    client, factory = env
    register(client)
    login(client)
    with factory.begin() as db:
        db.get(User, "staff").active = False
    assert command(client, "/api/counters/counter/call").status_code == 409
    assert not client.get("/api/board").json()["counters"][0]["staffed"]
    with factory.begin() as db:
        db.get(User, "staff").active = True
        db.get(Counter, "counter").active = False
    assert command(client, "/api/counters/counter/call").status_code == 409


def test_estimate_uses_remaining_load_and_completed_samples(env):
    client, factory = env
    first = register(client).json()
    second = register(client).json()
    assert second["eta_minutes"] == 10
    login(client, "staff")
    command(client, "/api/counters/counter/call")
    with factory.begin() as db:
        db.get(Ticket, first["id"]).started = now() - timedelta(minutes=5)
    second_now = client.get(f"/api/tickets/{second['secret']}").json()
    assert 4 <= second_now["eta_minutes"] <= 5
    command(client, "/api/counters/counter/complete")
    third = register(client).json()
    assert 4 <= third["eta_minutes"] <= 6


def test_inactive_service_and_successful_service_update(env):
    client, _ = env
    login(client)
    response = client.put(
        "/api/admin/services/svc",
        json={"name": "Updated consultation", "minutes": 20, "capacity": 3, "active": False},
    )
    assert response.status_code == 200
    assert client.get("/api/services").json() == []
    assert register(client).status_code == 409
    assert client.get(f"/api/services/svc/slots?day={(now() + timedelta(days=1)).date()}").json() == []


def test_staff_cannot_operate_another_staff_counter(env):
    client, factory = env
    with factory.begin() as db:
        db.get(Counter, "counter").staff_id = "admin"
    login(client, "staff")
    assert command(client, "/api/counters/counter/call").status_code == 403


def test_unknown_actions_and_expired_session(env):
    client, factory = env
    from app.models import LoginSession

    assert command(client, "/api/tickets/missing/unknown").status_code == 404
    login(client)
    assert command(client, "/api/counters/counter/unknown").status_code == 404
    with factory.begin() as db:
        db.scalar(select(LoginSession)).expires = now() - timedelta(seconds=1)
    assert client.get("/api/auth/me").status_code == 401


def test_bootstrap_validation_and_repeatability(env, monkeypatch):
    _, factory = env
    from app import seed
    import pytest

    monkeypatch.setattr(seed, "SessionLocal", factory)
    monkeypatch.setattr(seed.settings, "admin_password", "short")
    with pytest.raises(ValueError):
        seed.seed()
    monkeypatch.setattr(seed.settings, "admin_password", "unique-long-password")
    seed.seed()
    with factory() as db:
        assert len(db.scalars(select(User)).all()) == 4
