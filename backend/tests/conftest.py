import os
from uuid import uuid4
import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app.db import get_db, make_engine
from app.main import app
from app.models import Base, Counter, Organization, Service, User
from app.security import password_hash

TEST_PASSWORD_HASH = password_hash("test-password-123")


@pytest.fixture
def env(tmp_path):
    postgres_url = os.environ.get("TEST_DATABASE_URL")
    schema = "test_" + uuid4().hex
    admin_engine = make_engine(postgres_url) if postgres_url else None
    if admin_engine:
        with admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        from sqlalchemy import create_engine

        engine = create_engine(postgres_url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as db:
        db.add_all([Organization(id="main", name="Test branch"), Organization(id="other", name="Other")])
        db.flush()
        db.add_all(
            [
                Service(id="svc", org_id="main", name="Consultation", minutes=10, capacity=2),
                Service(id="other-svc", org_id="other", name="Private", minutes=10, capacity=1),
            ]
        )
        for identifier, role, org in [
            ("admin", "admin", "main"),
            ("staff", "staff", "main"),
            ("reception", "receptionist", "main"),
            ("other-admin", "admin", "other"),
        ]:
            db.add(
                User(
                    id=identifier,
                    org_id=org,
                    email=f"{identifier}@example.com",
                    name=identifier,
                    password_hash=TEST_PASSWORD_HASH,
                    role=role,
                )
            )
        db.flush()
        db.add_all(
            [
                Counter(id="counter", org_id="main", name="Counter 01", service_id="svc", staff_id="staff"),
                Counter(
                    id="other-counter",
                    org_id="other",
                    name="Secret",
                    service_id="other-svc",
                    staff_id="other-admin",
                ),
            ]
        )

    def override():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()
    if admin_engine:
        with admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin_engine.dispose()


def login(client, role="admin"):
    response = client.post(
        "/api/auth/login", json={"email": f"{role}@example.com", "password": "test-password-123"}
    )
    assert response.status_code == 200, response.text


def register(client, **changes):
    from uuid import uuid4

    payload = {"name": "Test Visitor", "service_id": "svc", "source": "walk_in", **changes}
    return client.post("/api/tickets", json=payload, headers={"Idempotency-Key": uuid4().hex})
