import hashlib
import hmac
import secrets
from datetime import timedelta
from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session
from .db import get_db
from .models import LoginSession, User, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password: str) -> str:
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()


def verify_password(password: str, encoded: str) -> bool:
    salt, expected = encoded.split(":")
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    return hmac.compare_digest(actual, expected)


def utc(value):
    from datetime import timezone

    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def current_user(qp_session: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User:
    session = db.get(LoginSession, digest(qp_session or ""))
    if not session or utc(session.expires) <= now():
        raise HTTPException(401, "Sign in required")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "Account unavailable")
    return user


def roles(*allowed):
    def authorize(user: User = Depends(current_user)):
        if user.role not in allowed:
            raise HTTPException(403, "Insufficient permissions")
        return user

    return authorize


def create_session(db, user):
    token = secrets.token_urlsafe(48)
    db.add(LoginSession(digest=digest(token), user_id=user.id, expires=now() + timedelta(hours=8)))
    return token
