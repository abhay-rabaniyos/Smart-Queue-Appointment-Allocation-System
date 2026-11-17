# Local validation

Validation date: 17 November 2026.

- Backend: 49 tests passed with 94% statement coverage, including workflow, concurrency, SMTP/Twilio/webhook adapters, configuration, and frozen migration upgrade/downgrade checks.
- Frontend: 8 tests passed; TypeScript validation and Vite production build passed, including stable idempotency keys after network failures.
- Dependency audit: zero frontend vulnerabilities after updating Vitest to 4.1.12.
- Real notification providers: SMTP, direct Twilio SMS/WhatsApp, and generic HTTPS gateway tested with mocks; no provider credentials supplied and no real messages sent.
- PostgreSQL / Docker: not available locally. PostgreSQL test execution and migration smoke checks are configured in CI.
- Browser smoke test: a walk-in registration generated a private QR pass and its token appeared on the live queue board. Layout inspected at the browser's available viewport. Full cross-browser, mobile-device, and sustained load testing remain deployment checks.
