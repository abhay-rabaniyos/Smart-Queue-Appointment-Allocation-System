"""Explicit, repeatable bootstrap; application startup never creates schemas or demo credentials."""

import argparse
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import select
from .config import settings
from .db import SessionLocal
from .models import Counter, Organization, Service, User
from .security import password_hash, verify_password


def seed():
    if len(settings.admin_password) < 12 or settings.admin_password.startswith("REPLACE_"):
        raise ValueError("Set admin_password to a unique password of at least 12 characters")
    with SessionLocal.begin() as db:
        if db.get(Organization, settings.organization_id):
            print("Organization exists; bootstrap skipped")
            return
        db.add(Organization(id=settings.organization_id, name=settings.organization_name))
        db.flush()
        user = User(
            org_id=settings.organization_id,
            email=settings.admin_email.lower(),
            name="Administrator",
            role="admin",
            password_hash=password_hash(settings.admin_password),
        )
        service = Service(
            org_id=settings.organization_id, name="General consultation", minutes=10, capacity=2
        )
        db.add_all([user, service])
        db.flush()
        db.add(
            Counter(
                org_id=settings.organization_id, name="Counter 01", service_id=service.id, staff_id=user.id
            )
        )
    print("Organization, administrator, service and counter created")


def seed_demo():
    """Opt-in public demo accounts; never overwrite existing passwords or roles."""
    values = dotenv_values(Path(__file__).resolve().parents[1] / "demo.properties")
    with SessionLocal.begin() as db:
        org = db.get(Organization, settings.organization_id)
        if not org:
            db.add(Organization(id=settings.organization_id, name=settings.organization_name))
            db.flush()
        accounts = {}
        for role, name in (
            ("admin", "Demo Administrator"),
            ("receptionist", "Demo Receptionist"),
            ("staff", "Demo Service Staff"),
        ):
            email, password = values[f"{role}_email"], values[f"{role}_password"]
            if not email or not password or len(password) < 12:
                raise ValueError("Demo account properties are incomplete")
            user = db.scalar(select(User).where(User.email == email))
            if user:
                if (
                    user.org_id != settings.organization_id
                    or user.role != role
                    or not user.active
                    or not verify_password(password, user.password_hash)
                ):
                    raise ValueError(
                        f"Demo email conflicts with an existing account: {email}; no accounts changed"
                    )
            else:
                user = User(
                    org_id=settings.organization_id,
                    email=email,
                    name=name,
                    role=role,
                    password_hash=password_hash(password),
                )
                db.add(user)
                db.flush()
            accounts[role] = user
        service = db.scalar(
            select(Service)
            .where(Service.org_id == settings.organization_id, Service.active.is_(True))
            .order_by(Service.id)
        )
        if not service:
            service = Service(
                org_id=settings.organization_id, name="General consultation", minutes=10, capacity=2
            )
            db.add(service)
            db.flush()
        if not db.scalar(select(Counter.id).where(Counter.staff_id == accounts["staff"].id)):
            db.add(
                Counter(
                    org_id=settings.organization_id,
                    name="Demo Counter",
                    service_id=service.id,
                    staff_id=accounts["staff"].id,
                )
            )
    print("Public demo accounts ready. Credentials are in demo.properties; never use them in production.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Initialize QueuePilot accounts")
    parser.add_argument("--demo", action="store_true", help="Create opt-in public demo accounts")
    args = parser.parse_args()
    seed_demo() if args.demo else seed()
