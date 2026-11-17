"""Explicit, repeatable bootstrap; application startup never creates schemas or demo credentials."""

from .config import settings
from .db import SessionLocal
from .models import Counter, Organization, Service, User
from .security import password_hash


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


if __name__ == "__main__":
    seed()
