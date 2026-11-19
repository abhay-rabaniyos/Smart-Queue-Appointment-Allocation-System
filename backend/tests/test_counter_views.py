from app.models import Counter, Service, User
from .conftest import login, register
from .test_workflows import command


def test_shared_service_counts_and_distinct_current_tokens(env):
    client, factory = env
    with factory.begin() as db:
        db.add(Counter(id="second", org_id="main", name="Counter 02", service_id="svc", staff_id="admin"))
    first = register(client).json()
    assert first["service_name"] == "Consultation"
    second = register(client).json()
    summaries = client.get("/api/board").json()["counters"]
    assert all(c["waiting_count"] == 2 and c["availability"] == "available" for c in summaries)
    login(client)
    called = command(client, "/api/counters/counter/call").json()
    assert called["id"] == first["id"]
    views = {c["id"]: c for c in client.get("/api/board").json()["counters"]}
    assert views["counter"]["serving_token"] == first["token"]
    assert views["counter"]["availability"] == "serving"
    assert views["second"]["serving_token"] is None
    assert views["second"]["availability"] == "available"
    assert all(c["waiting_count"] == 1 for c in views.values())
    assert command(client, "/api/counters/second/call").json()["id"] == second["id"]
    command(client, "/api/counters/counter/complete")
    views = {c["id"]: c for c in client.get("/api/operations").json()["counter_summaries"]}
    assert views["counter"]["serving_token"] is None
    assert views["counter"]["availability"] == "available"
    assert views["second"]["serving_token"] == second["token"]


def test_public_counter_summary_has_no_staff_or_customer_identity(env):
    client, _ = env
    register(client, contact="private@example.com")
    summary = client.get("/api/board").json()["counters"][0]
    assert summary["service_name"] == "Consultation"
    assert not {"staff_id", "staff_name", "email", "name_of_customer", "secret", "contact"} & summary.keys()
    assert "other-counter" not in str(client.get("/api/board").json())
    login(client, "other-admin")
    operations = client.get("/api/operations").json()
    assert {c["id"] for c in operations["counter_summaries"]} == {"other-counter"}


def test_counter_availability_explains_unavailable_states(env):
    client, factory = env
    with factory.begin() as db:
        db.get(Counter, "counter").active = False
    assert client.get("/api/board").json()["counters"][0]["availability"] == "paused"
    with factory.begin() as db:
        db.get(Counter, "counter").active = True
        db.get(User, "staff").active = False
    assert client.get("/api/board").json()["counters"][0]["availability"] == "unstaffed"
    with factory.begin() as db:
        db.get(User, "staff").active = True
        db.get(Service, "svc").active = False
    assert client.get("/api/board").json()["counters"][0]["availability"] == "service_unavailable"
