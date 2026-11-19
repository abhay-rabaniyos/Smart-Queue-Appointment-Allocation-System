# QueuePilot

React + TypeScript and FastAPI queue and appointment application. Supports online bookings, self-service walk-ins, reception registration, QR queue passes, live tracking, staff counters, priority aging, rescheduling, cancellation, analytics, audit history, and durable notification delivery.

## Run locally on Windows

Requirements: Python 3.12+, uv, and Node 20.19+ (Node 22 recommended). The downloaded project-local Python under `.tools/python/` can also be used. Private credentials are read from local configuration; opt-in public demo credentials are provided separately.

```powershell
./scripts/init-local.ps1
cd backend
uv sync --frozen --python 3.12
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

In a third terminal, run the worker (required for notification delivery and no-show expiration):

```powershell
cd backend
uv run python -m app.worker
```

Open [QueuePilot](http://localhost:5173), then **Service desk** to sign in. Read `admin_email` and the generated `admin_password` from your ignored `backend/config.properties`. Bootstrap creates one organization, one service, one admin, and a staffed counter. It is repeatable and never resets existing credentials. API documentation: [Swagger UI](http://localhost:8000/docs).

If using the bundled interpreter rather than an installed Python:

```powershell
uv sync --project backend --python .tools/python/cpython-3.12.16-windows-x86_64-none/python.exe
```

Once the environment exists, run `backend/.venv/Scripts/python.exe` directly from the appropriate working directory, or use `uv run --no-sync` inside `backend`.

## Sharing a local demo through ngrok

Keep FastAPI running on `127.0.0.1:8000` and Vite on port `5173`. Run `ngrok http http://127.0.0.1:5173` in another terminal. Only Vite's port needs a tunnel: `/api` HTTP requests and WebSocket updates are proxied to FastAPI internally.

Add your exact ngrok hostname to `server.allowedHosts` in `frontend/vite.config.ts`. The current configured hostname is `battery-pencil-paltry.ngrok-free.dev`. In your ignored `backend/config.properties`, include `https://battery-pencil-paltry.ngrok-free.dev` in `cors_origins` and set `public_url` to that HTTPS URL so QR passes open through the tunnel. Restart FastAPI and Vite after changes. Update these three settings if your ngrok hostname changes. Keep the worker running if testing notifications or no-show handling.

This exposes the local demo, including any enabled public demo logins, to anyone with the tunnel address. Use test data. The Vite development server is intended for temporary demonstrations; use the production deployment for ongoing hosting.

## Demo logins for GitHub clones

To create all three demo roles, run from `backend/` after installing dependencies and applying migrations:

```powershell
uv run python -m app.seed --demo
```

| Role | Email | Password (plain text for signing in) |
| --- | --- | --- |
| Administrator | `admin.demo@example.com` | `QueuePilotDemo!2026` |
| Receptionist | `reception.demo@example.com` | `QueuePilotDemo!2026` |
| Service staff | `staff.demo@example.com` | `QueuePilotDemo!2026` |

Sign in through **Service desk**. The accounts are created only by `--demo`, not automatically when cloning or starting the app. The command also creates a staffed demo counter. It can be run again without duplicating accounts or resetting passwords. Conflicting existing accounts cause a rollback instead of overwriting them.

These intentionally public credentials are in `backend/demo.properties`; use them only for local demos. Database passwords remain hashed. Your private generated administrator credentials remain excluded from GitHub. For production, use the normal bootstrap and unique passwords. Customers use private queue passes and do not need login accounts.

## PostgreSQL with Docker

Copy `.env.example` to `.env`, replace both passwords with unique random values (URL-safe characters for the database password), then:

```sh
docker compose up --build
```

Open [the application](http://localhost:8080). Compose runs PostgreSQL, migrations/bootstrap, the API, worker, and an Nginx-served React build. Database storage persists in a named volume. For Compose, configure notification provider credentials in the root `.env`; local Python processes read `backend/config.properties`. Docker is not installed on the build machine, so this deployment path and PostgreSQL execution are provided for CI/deployment validation, not claimed as locally tested.

## Configuration and credentials

`backend/config.properties.example` documents all application properties. Copy it to `backend/config.properties` for PostgreSQL/manual setup, or use `scripts/init-local.ps1` for SQLite development. Run the backend from `backend/` so it finds the file. Property names are case-insensitive; environment variables override file values. Lists use JSON. The browser receives no database password, session secret, or provider credentials. Commit only example files; real configuration, `.env`, local databases, and `.tools` are ignored.

| Setting | Purpose |
| --- | --- |
| `database_url` | PostgreSQL in deployment; SQLite for local development/tests |
| `organization_id` | Public portal's organization; staff access uses the authenticated account's organization |
| `timezone` | Branch scheduling timezone, defaults to Asia/Kolkata |
| `cors_origins` | Exact allowed frontend origins, including WebSocket origins |
| `public_url` | URL encoded in QR queue passes |
| `cookie_secure` | Set `true` behind production HTTPS |
| `admin_email`, `admin_password` | Explicit initial bootstrap credentials |
| `notification_mode` | `console`, `smtp`, `providers`, or `webhook` |

Production requires HTTPS, secure cookies, a reverse proxy with request/body limits, trusted host/origin configuration, managed secrets, database backups, and a deployment-specific data retention policy. Do not enable access logs containing private ticket URLs. The included Nginx config suppresses API URL logs. Use a separate organization configuration for each public portal; staff accounts remain organization-scoped. No public organization creation is exposed.

## Notifications

- `console`: marks delivery as **simulated**, without logging recipient details. Useful for a local demo.
- `smtp`: uses STARTTLS, configured SMTP credentials, and deterministic Message-ID values. Supports email; unsupported channels retry and eventually enter the dead-letter state.
- `providers`: email uses SMTP; SMS and WhatsApp use Twilio directly. Set the `twilio_*` properties in the example file. WhatsApp uses an approved Content template with variables `1` = token, `2` = event name, `3` = status. Supply an approved sender and obtain customer opt-in before live use. The integration follows the [Twilio Messages resource](https://www.twilio.com/docs/messaging/api/message-resource).
- `webhook`: POSTs to a configured HTTPS gateway for email/SMS/WhatsApp. Supply a gateway that integrates your chosen providers and consent/template requirements. The request includes `event_id`, `channel`, `to`, `message`, a bearer token, and an `Idempotency-Key` header.

Delivery is **at least once**. The gateway must deduplicate event IDs. Direct SMTP/Twilio delivery does not guarantee deduplication after an ambiguous timeout. The outbox state `sent` means the provider accepted the submission, not confirmed delivery to the recipient. Five failed attempts result in a dead letter; administrators can retry it from the dashboard. External services were tested with mocks; real messages require credentials and provider testing.

## Architecture and invariants

```text
React customer / reception / staff / admin UI
                    | REST commands + WebSocket snapshots
FastAPI routes -> QueueService -> SQLAlchemy transaction -> PostgreSQL
                    |                 | ticket + inbox + outbox + audit
              QueuePolicy        notification worker -> provider adapter
```

HTTP schemas validate inputs; route dependencies enforce roles; the application service owns state transitions and the transaction boundary; the queue policy and notification sender are replaceable protocols. SQLAlchemy's session acts as the unit of work. Domain policy is separate from storage and transport. Avoiding a pass-through repository for every model keeps the abstraction useful rather than ceremonial.

- **Inbox / idempotency:** booking, ticket lifecycle and dispatch commands require an 8–80 character `Idempotency-Key`. Each operation stores a request fingerprint and response atomically with the mutation. Identical retries replay the result; changed payloads return 409. Do not generate a new key when retrying an uncertain command. Administrative configuration creates use normal REST semantics and database constraints rather than inbox replay.
- **Atomic queue operations:** lock the organization row with PostgreSQL `FOR UPDATE` before checking capacity, allocating sequences, or dispatching. SQLite obtains a write lock for local tests. All writers use the same lock order. Requests for separate organizations can proceed independently; a single organization's writes are intentionally serialized.
- **Outbox:** notification work and audit entries commit alongside queue state. A worker claims PostgreSQL rows with `SKIP LOCKED`, retries with exponential backoff, and preserves dead letters. Real-time boards use durable database snapshots every two seconds, so reconnects and API replicas recover state without relying on process memory.
- **Lifecycle:** `booked → waiting → serving → completed`; booked/waiting may cancel. Only booked appointments may reschedule. Check-in opens 30 minutes before the slot; configurable grace defaults to 15 minutes. The worker marks overdue bookings `no_show` and releases their capacity. Walk-ins enter `waiting` immediately.
- **Scheduling:** branch hours are currently 09:00–17:00 every day, configurable per-service slot duration/capacity, and a 30-day booking horizon. Priority is staff-assigned, with score `priority × weight + minutes_waited / aging_interval`. Unbounded aging prevents starvation. This is operational queue ordering, not clinical triage.
- **Allocation:** each counter has a service and one active staff assignment. A staff member can serve at only one counter. Call-next selects the highest-ranked eligible visitor and rejects busy/unavailable counters. Administrators can allocate eligible visitors across all idle counters in one transaction, reassign idle counters and pause them. Staff can operate only their assigned counter.
- **ETA:** schedules preceding visitors across staffed counters using their remaining loads and the mean of the last 30 completed visits for that service. Falls back to the configured duration; returns `null` when no staffed counter is available. ETA is an estimate, not a promise.
- **Privacy:** random 256-bit ticket capabilities permit customer management without an account. Treat the queue pass like a private link. Public boards expose tokens, service/counter IDs and estimates only. Staff sessions use hashed opaque tokens, HttpOnly/SameSite cookies, PBKDF2 password hashes, expiry, and origin checks.
- **Analytics:** dashboard statistics describe the latest 500 registrations, and audit/notification views show the latest 50 events. They are explicitly bounded, not all-time reporting.

## Tests

### UI errors

API validation/action failures, network/timeouts, background refresh failures and live-update failures use a shared dismissible error panel, visible even when the page is scrolled. Repeated identical failures show one alert per continuing incident; dismissing it suppresses repeats until recovery, after which a new failure may be shown. Ordinary anonymous `/auth/me` responses do not trigger sign-in errors. SMTP/provider failures surface as safe explanatory messages in staff views and on the affected customer's private ticket (updated by polling). Public boards do not expose delivery errors or recipient details. Invalid email syntax is rejected before registration; SMTP can still reject a correctly formatted address. Dead-letter errors explain that automatic retries have stopped. Native required-field validation and the React error boundary remain in place for form and rendering errors.

### Counter views

The appointments/visitors table shows each ticket's service and supports service and counter filters together. Ticket and board APIs include service names so existing visits remain understandable when a service is inactive or absent from the public booking list. Queue passes explicitly label the requested service and include it in the call-to-counter message.

Customers see a counter directory, service-specific counter availability during registration, eligible counter routing on the live board, and their assigned counter on the queue pass after being called. Availability distinguishes ready, serving, paused, no active staff, and unavailable services. Staff names and roles are shown only in authenticated counter workspaces. All staff roles can view counter context; service staff can operate only their own counter, administrators can operate all counters, and receptionists have a read-only counter view. The visitor table can be filtered by counter, including unassigned visitors in that counter's shared service queue. Waiting counts are per service and must not be added together across counters handling the same service.

```powershell
cd backend
uv run pytest --cov=app --cov-report=term-missing -q
uv run ruff check app tests
cd ../frontend
npm test
npm run build
npm audit
```

Backend tests cover queue transitions, double-booking, concurrent registration and dispatch, duplicate commands, priority aging, rollback, role and organization boundaries, stale check-ins, invalid data, QR images, WebSocket origin checks, properties loading, SMTP/webhook adapters and dead letters. Frontend tests cover booking guards, walk-in registration, pass display, staff login, empty states and error handling.

To run the same suite against a **disposable** PostgreSQL database, set `TEST_DATABASE_URL` before pytest. Tests create a unique schema per case and drop only that schema afterward. GitHub Actions runs both SQLite and PostgreSQL suites, plus migrations, lint, frontend tests, build and dependency audit. CI has been configured but has not been executed remotely in this workspace.

See [docs/VALIDATION.md](docs/VALIDATION.md) for actual local results and remaining validation boundaries.
