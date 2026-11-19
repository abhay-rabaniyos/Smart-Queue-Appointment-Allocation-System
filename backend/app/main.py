import asyncio
import io
from datetime import date, timedelta
from typing import Annotated
import qrcode
from fastapi import Depends, FastAPI, Header, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from .config import settings
from .db import SessionLocal, get_db
from .models import (
    Audit,
    Counter,
    LoginAttempt,
    LoginSession,
    Organization,
    Outbox,
    Service,
    Ticket,
    User,
    now,
)
from .schemas import (
    CounterInput,
    Login,
    Registration,
    Reschedule,
    RulesInput,
    ServiceInput,
    StaffInput,
    StaffUpdate,
)
from .security import create_session, current_user, digest, password_hash, roles, utc, verify_password
from .services import QueueService, fail

app = FastAPI(title="QueuePilot API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Idempotency-Key"],
)
Db = Annotated[Session, Depends(get_db)]
Key = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
]
Admin = Annotated[User, Depends(roles("admin"))]
Reception = Annotated[User, Depends(roles("admin", "receptionist"))]
Operator = Annotated[User, Depends(roles("admin", "staff"))]


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            return Response(status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=409, content={"detail": "Conflicting assignment or duplicate resource"})


def execute(db, org_id, actor, key, operation, payload, callback):
    service = QueueService(db, org_id, actor)
    try:
        result = service.command(key, operation, payload, lambda: callback(service))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@app.get("/api/health")
def health(db: Db):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: Login, response: Response, db: Db, request: Request):
    # Login failures persist, including across API processes. Reverse proxy must sanitize forwarded IPs.
    key = digest(f"{request.client.host}:{str(data.email).lower()}")
    attempt = db.scalar(select(LoginAttempt).where(LoginAttempt.key == key).with_for_update())
    if attempt and utc(attempt.window) > now() - timedelta(minutes=15) and attempt.count >= 10:
        fail("Too many attempts; try again in 15 minutes", 429)
    user = db.scalar(select(User).where(User.email == str(data.email).lower(), User.active.is_(True)))
    encoded = user.password_hash if user else password_hash("invalid-account-placeholder")
    if not verify_password(data.password, encoded) or not user:
        if not attempt:
            attempt = LoginAttempt(key=key, count=0, window=now())
            db.add(attempt)
        if utc(attempt.window) < now() - timedelta(minutes=15):
            attempt.count, attempt.window = 0, now()
        attempt.count += 1
        db.commit()
        fail("Invalid email or password", 401)
    token = create_session(db, user)
    if attempt:
        db.delete(attempt)
    db.commit()
    response.set_cookie(
        "qp_session", token, httponly=True, secure=settings.cookie_secure, samesite="strict", max_age=28800
    )
    return {"id": user.id, "name": user.name, "role": user.role}


@app.get("/api/auth/me")
def me(user: Annotated[User, Depends(current_user)]):
    return {"id": user.id, "name": user.name, "role": user.role}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: Db):
    entry = db.get(LoginSession, digest(request.cookies.get("qp_session", "")))
    if entry:
        db.delete(entry)
        db.commit()
    response.delete_cookie("qp_session")
    return {"ok": True}


@app.get("/api/services")
def services(db: Db):
    return db.scalars(
        select(Service).where(Service.org_id == settings.organization_id, Service.active.is_(True))
    ).all()


@app.get("/api/services/{service_id}/slots")
def slots(service_id: str, day: date, db: Db):
    return QueueService(db, settings.organization_id).slots(service_id, day)


@app.post("/api/tickets", status_code=201)
def register(data: Registration, key: Key, db: Db):
    return execute(
        db,
        settings.organization_id,
        "customer",
        key,
        "register",
        data.model_dump(mode="json"),
        lambda s: s.register(data),
    )


@app.post("/api/reception/tickets", status_code=201)
def reception_register(data: Registration, key: Key, db: Db, user: Reception):
    return execute(
        db,
        user.org_id,
        user.id,
        key,
        "reception-register",
        data.model_dump(mode="json"),
        lambda s: s.register(data, True),
    )


@app.get("/api/tickets/{secret}")
def ticket(secret: str, db: Db):
    service = QueueService(db, settings.organization_id)
    return service.private_ticket(service.by_secret(secret))


@app.get("/api/tickets/{secret}/qr")
def qr(secret: str, db: Db):
    QueueService(db, settings.organization_id).by_secret(secret)
    image = qrcode.make(f"{settings.public_url}/#ticket={secret}")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@app.post("/api/tickets/{secret}/reschedule")
def reschedule(secret: str, data: Reschedule, key: Key, db: Db):
    return execute(
        db,
        settings.organization_id,
        "customer",
        key,
        "reschedule",
        {"secret": secret, **data.model_dump(mode="json")},
        lambda s: s.change(secret, "reschedule", data.slot),
    )


@app.post("/api/tickets/{secret}/{action}")
def change_ticket(secret: str, action: str, key: Key, db: Db):
    if action not in ("check-in", "cancel"):
        fail("Unknown action", 404)
    return execute(
        db,
        settings.organization_id,
        "customer",
        key,
        action,
        {"secret": secret},
        lambda s: s.change(secret, action),
    )


@app.get("/api/board")
def board(db: Db):
    return QueueService(db, settings.organization_id).board()


@app.websocket("/api/ws/board")
async def board_socket(ws: WebSocket):
    if ws.headers.get("origin") not in settings.cors_origins:
        await ws.close(code=1008)
        return
    await ws.accept()

    def snapshot():
        with SessionLocal() as db:
            return QueueService(db, settings.organization_id).board()

    try:
        while True:
            # Database snapshots survive reconnects and work across API replicas.
            await ws.send_json(await run_in_threadpool(snapshot))
            await asyncio.sleep(2)
    except (WebSocketDisconnect, RuntimeError):
        pass


@app.post("/api/counters/{counter_id}/{action}")
def counter_action(counter_id: str, action: str, key: Key, db: Db, user: Operator):
    if action not in ("call", "complete"):
        fail("Unknown action", 404)
    return execute(
        db,
        user.org_id,
        user.id,
        key,
        action,
        {"counter": counter_id},
        lambda s: s.dispatch(counter_id, user) if action == "call" else s.complete(counter_id, user),
    )


@app.get("/api/operations")
def operations(db: Db, user: Annotated[User, Depends(current_user)]):
    service = QueueService(db, user.org_id, user.id)
    tickets = db.scalars(
        select(Ticket).where(Ticket.org_id == user.org_id).order_by(Ticket.created.desc()).limit(500)
    ).all()
    completed = [t for t in tickets if t.status == "completed"]
    waits = [(utc(t.started) - utc(t.checked_in)).total_seconds() / 60 for t in completed]
    estimates = {}
    for service_id in {t.service_id for t in tickets if t.status == "waiting"}:
        estimates.update(service.estimates(service_id))
    return {
        "tickets": [service.private_ticket(t, estimates) for t in tickets],
        "counters": db.scalars(select(Counter).where(Counter.org_id == user.org_id)).all(),
        "counter_summaries": service.counter_summaries(),
        "services": db.scalars(select(Service).where(Service.org_id == user.org_id)).all(),
        "staff": [
            {"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.active}
            for u in db.scalars(select(User).where(User.org_id == user.org_id))
        ],
        "rules": {
            "aging_minutes": db.get(Organization, user.org_id).aging_minutes,
            "priority_weight": db.get(Organization, user.org_id).priority_weight,
            "grace_minutes": db.get(Organization, user.org_id).grace_minutes,
        },
        "analytics": {
            "completed": len(completed),
            "average_wait": round(sum(waits) / len(waits), 1) if waits else 0,
            "waiting": sum(t.status == "waiting" for t in tickets),
            "no_shows": sum(t.status == "no_show" for t in tickets),
            "sample_limit": 500,
        },
        "outbox": [
            {"id": e.id, "kind": e.kind, "state": e.state, "attempts": e.attempts, "error": e.error}
            for e in db.scalars(
                select(Outbox).where(Outbox.org_id == user.org_id).order_by(Outbox.created.desc()).limit(50)
            )
        ],
        "audit": db.scalars(
            select(Audit).where(Audit.org_id == user.org_id).order_by(Audit.created.desc()).limit(50)
        ).all(),
    }


@app.post("/api/admin/services", status_code=201)
def add_service(data: ServiceInput, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    obj = Service(org_id=user.org_id, **data.model_dump())
    db.add(obj)
    db.flush()
    service.record("service_created", obj.id)
    db.commit()
    return obj


@app.post("/api/admin/dispatch")
def allocate_available_counters(key: Key, db: Db, user: Admin):
    def allocate(service):
        results = []
        counters = db.scalars(
            select(Counter)
            .join(User, Counter.staff_id == User.id)
            .join(Service, Counter.service_id == Service.id)
            .where(
                Counter.org_id == user.org_id,
                Counter.active.is_(True),
                User.active.is_(True),
                Service.active.is_(True),
            )
            .order_by(Counter.id)
        ).all()
        for counter in counters:
            busy = db.scalar(
                select(Ticket.id).where(Ticket.counter_id == counter.id, Ticket.status == "serving")
            )
            if not busy and service.ordered(counter.service_id):
                results.append(service.dispatch(counter.id, user))
        return {"allocated": results}

    return execute(db, user.org_id, user.id, key, "auto-dispatch", {}, allocate)


@app.put("/api/admin/services/{identifier}")
def update_service(identifier: str, data: ServiceInput, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    obj = service.get(Service, identifier)
    if db.scalar(
        select(Ticket.id).where(
            Ticket.service_id == identifier, Ticket.status.in_(("booked", "waiting", "serving"))
        )
    ):
        fail("Resolve active tickets before changing service configuration")
    for key, value in data.model_dump().items():
        setattr(obj, key, value)
    service.record("service_updated", obj.id)
    db.commit()
    return obj


@app.post("/api/admin/staff", status_code=201)
def add_staff(data: StaffInput, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    obj = User(
        org_id=user.org_id,
        email=str(data.email).lower(),
        name=data.name,
        role=data.role,
        password_hash=password_hash(data.password),
    )
    db.add(obj)
    db.flush()
    service.record("staff_created", obj.id)
    db.commit()
    return {"id": obj.id}


@app.put("/api/admin/staff/{identifier}")
def update_staff(identifier: str, data: StaffUpdate, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    obj = service.get(User, identifier)
    if obj.id == user.id and not data.active:
        fail("Cannot disable your own account")
    counter = db.scalar(select(Counter).where(Counter.staff_id == identifier))
    if (
        not data.active
        and counter
        and db.scalar(select(Ticket.id).where(Ticket.counter_id == counter.id, Ticket.status == "serving"))
    ):
        fail("Finish the active customer first")
    obj.active = data.active
    service.record("staff_updated", identifier)
    db.commit()
    return {"ok": True}


def save_counter(data, db, user, identifier=None):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    service.get(Service, data.service_id)
    if data.staff_id:
        staff = service.get(User, data.staff_id)
        if not staff.active or staff.role not in ("admin", "staff"):
            fail("Choose an active service staff member")
    counter = service.get(Counter, identifier) if identifier else Counter(org_id=user.org_id)
    if identifier and db.scalar(
        select(Ticket.id).where(Ticket.counter_id == identifier, Ticket.status == "serving")
    ):
        fail("Finish the active customer before changing this counter")
    for key, value in data.model_dump().items():
        setattr(counter, key, value)
    db.add(counter)
    db.flush()
    service.record("counter_updated", counter.id)
    db.commit()
    return counter


@app.post("/api/admin/counters", status_code=201)
def add_counter(data: CounterInput, db: Db, user: Admin):
    return save_counter(data, db, user)


@app.put("/api/admin/counters/{identifier}")
def update_counter(identifier: str, data: CounterInput, db: Db, user: Admin):
    return save_counter(data, db, user, identifier)


@app.put("/api/admin/rules")
def update_rules(data: RulesInput, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    org = service.lock()
    for key, value in data.model_dump().items():
        setattr(org, key, value)
    service.record("rules_updated", user.org_id)
    db.commit()
    return data


@app.post("/api/admin/outbox/{identifier}/retry")
def retry_notification(identifier: str, db: Db, user: Admin):
    service = QueueService(db, user.org_id, user.id)
    service.lock()
    event = service.get(Outbox, identifier)
    if event.state != "dead":
        fail("Only dead letters can be retried")
    event.state, event.attempts, event.available, event.error = "pending", 0, now(), None
    service.record("notification_retried", identifier)
    db.commit()
    return {"ok": True}
