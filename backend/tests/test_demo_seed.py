from sqlalchemy import func, select
import pytest
from app import seed
from app.models import Counter, Organization, User
from app.security import password_hash, verify_password


def test_demo_accounts_are_repeatable_hashed_and_can_login(env, monkeypatch):
    client, factory = env
    monkeypatch.setattr(seed, "SessionLocal", factory)
    seed.seed_demo()
    seed.seed_demo()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 7
        assert db.scalar(select(func.count()).select_from(Counter)) == 3
        for role, email in (
            ("admin", "admin.demo@example.com"),
            ("receptionist", "reception.demo@example.com"),
            ("staff", "staff.demo@example.com"),
        ):
            user = db.scalar(select(User).where(User.email == email))
            assert user.password_hash != "QueuePilotDemo!2026"
            assert verify_password("QueuePilotDemo!2026", user.password_hash)
            response = client.post(
                "/api/auth/login", json={"email": email, "password": "QueuePilotDemo!2026"}
            )
            assert response.status_code == 200
            assert response.json()["role"] == role


def test_demo_conflict_rolls_back_without_overwriting(env, monkeypatch):
    _, factory = env
    monkeypatch.setattr(seed, "SessionLocal", factory)
    with factory.begin() as db:
        db.add(
            User(
                org_id="other",
                email="staff.demo@example.com",
                name="Existing",
                role="staff",
                password_hash=password_hash("original-password"),
            )
        )
    with pytest.raises(ValueError, match="conflicts"):
        seed.seed_demo()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 5
        user = db.scalar(select(User).where(User.email == "staff.demo@example.com"))
        assert verify_password("original-password", user.password_hash)


def test_demo_can_bootstrap_empty_organization(env, monkeypatch):
    _, factory = env
    monkeypatch.setattr(seed, "SessionLocal", factory)
    monkeypatch.setattr(seed.settings, "organization_id", "fresh-demo")
    seed.seed_demo()
    with factory() as db:
        assert db.get(Organization, "fresh-demo")
        assert db.scalar(select(func.count()).select_from(User).where(User.org_id == "fresh-demo")) == 3
