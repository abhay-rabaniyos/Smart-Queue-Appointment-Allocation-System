from app.models import Service
from .conftest import register, login


def test_ticket_and_board_include_service_name_even_after_deactivation(env):
    client, factory = env
    ticket = register(client).json()
    assert client.get("/api/board").json()["tickets"][0]["service_name"] == "Consultation"
    with factory.begin() as db:
        db.get(Service, "svc").active = False
    assert client.get("/api/services").json() == []
    assert client.get(f"/api/tickets/{ticket['secret']}").json()["service_name"] == "Consultation"
    login(client)
    assert client.get("/api/operations").json()["tickets"][0]["service_name"] == "Consultation"
