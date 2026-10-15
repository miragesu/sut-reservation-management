# Implementation Status

2026-10-15 (Asia/Taipei). **Day 1 implemented and locally validated; full MVP NOT DONE.** Production remote-build/LAN acceptance and hosted CI remain separate gates.

## Delivered Day 1 scope

- FastAPI factory, settings, public liveness, request IDs, safe error responses, authenticated OpenAPI, local Jinja2/Bootstrap assets and security headers.
- SQLAlchemy 2.x domain schema and initial Alembic revision `fd0b3a205c15`: users/sessions, labs, SUT lifecycle/operational fields, current usage, queues/offers, reservations/check-ins, permanent histories, audit and idempotent notifications. No runtime `create_all` or cascade deletion. See `docs/domain-states.md`.
- SQLite foreign keys/WAL/busy timeout and serialized `BEGIN IMMEDIATE` write transactions. Unique normalized SUT name within Lab, one usage per SUT with no per-user ownership constraint, queue uniqueness and interval/duration/state checks. Busy writers return 503/Retry-After.
- Argon2id local login, server-revocable signed sessions, HttpOnly/SameSite cookies, Secure default, CSRF for web/JSON mutations, login throttling, CLI-only one-time bootstrap, admin-created temporary accounts, mandatory password replacement before web/API access, password reset/change revoking all sessions.
- Super Admin account/role/status management; final active Super Admin protection under concurrent writes; resource impact preview and Needs attention; account disable/reactivation preserves activity. Self-profile allowlist, normalized unique email and safe audits.
- Lab/SUT API and browser management for either admin across all labs. Archive-only DELETE/restore, usage/queue/reservation guards, history retention, admin archive filter and immutable Lab assignment. Operational maintenance/out-of-service reasons, activity acknowledgement, preserved records, audit and persisted affected-user notices.
- Initial Dashboard Card default/Table toggle, shared search/Lab/platform/team/status filters, natural Name/Status ordering, effective/overdue status and server-time reservation summaries. Read-only 30-second polling retains controls/layout and signals stale/retry. Authenticated inventory/detail views.
- Digest-pinned Python 3.12 image, hash-locked requirements, non-root runtime, startup migration, one worker, healthcheck, configurable 5088:8000 and named SQLite volume. Production Compose requires an explicit reviewed Git ref; local-build override provided. Optional build CA secret preserves TLS verification behind corporate proxies.
- Synthetic development-only seed, pytest fixtures, browser/container smoke runners, GitHub Actions workflow, deployment/update/backup/restore guidance. No production data or secrets added.

## Verification evidence

Commands from repository root unless stated otherwise:

| Check | Result |
| --- | --- |
| `.venv/bin/ruff check backend scripts` | PASS |
| `.venv/bin/ruff format --check backend scripts` | PASS |
| `.venv/bin/pytest -q` | PASS: 39 tests, including auth/RBAC/CSRF, first-password gate, session invalidation, profile allowlist/email conflicts, CLI/seed repeatability, migration upgrade/check/downgrade/re-upgrade, inventory/HTML CRUD, archive guards/history preservation, maintenance activity, UTC/boundary projections, duplicate-name and last-admin races, Secure cookie, bounded SQLite contention and safe OpenAPI outputs |
| `.venv/bin/python -m compileall -q backend/app backend/alembic scripts` | PASS |
| `.venv/bin/python scripts/browser_smoke.py` | PASS: actual Chromium login/mandatory password change, 2 labs/20 synthetic SUTs, both layouts, shared filters/sort, real 30-second polling, unchanged controls, stale/retry, detail and profile; no page script errors |
| `DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt .venv/bin/python scripts/container_smoke.py` | PASS: Compose syntax/build/up, migration-before-listen, 5088 health/login, forced password change, inventory operations, non-root UID 10001, SQLite integrity, migration check and data/session persistence across down + rebuild/recreate. Broken migration prevents startup. Disposable project/volume cleaned up. |

The container builder initially could not resolve the inherited proxy and then lacked its trusted CA. The smoke resolves inherited proxy names and supplies the existing host-approved CA bundle as an ephemeral BuildKit secret; neither the CA nor proxy credentials are copied into the runtime image. TLS and package hash verification were retained. Browser runner CSP-sensitive JavaScript predicates were replaced with locator assertions; application CSP was preserved. One runner warning remains: Starlette deprecates its httpx TestClient integration; it does not skip or fail these tests.

## Unimplemented / unverified gates

- Day 2 coordination services/APIs/UI: Claim/Release/history creation, queue FIFO eligibility/expiry/promotion, reservations/edit/cancel/check-in/no-show, single restart-safe deadline processor and race/boundary tests. Schema and seeded test records do not establish these behaviors. No stub coordination endpoints exist.
- BR-017's queue pause/resume, new coordination-action guards and notices displayed to recipients await Day 2/3 integration. Day 1 persists notices and preserves activity; it does not claim the complete maintenance coordination workflow passes.
- Day 3 full notification/read/desktop opt-in UI, Dashboard Claim/Queue/Reserve modals, SUT Detail polling, Calendar/History screens and broader end-to-end/accessibility acceptance. The initial Dashboard's projections are tested using synthetic domain records; full MVP UI is not complete.
- SUT HTML inventory list has pagination; search/filter controls are on Dashboard and JSON inventory. The combined SUT-list acceptance item remains unchecked.
- Production clean-host public GitHub Remote Build from a published application commit is not yet verified. Set `SUT_GIT_REF` to the reviewed full application SHA; never use the original planning-only commit or `main` as a production pin. Local Compose build is verified independently.
- Actual internal Linux host/firewall, two LAN clients, backup/restore rehearsal and hosted GitHub Actions are unverified. Agent-local checks do not establish these outcomes.
- Git read access works via the platform HTTPS proxy. GitHub API requests currently return `Forbidden`; PR creation must be confirmed separately. No token values were inspected or copied.

Only specifically verified task items are checked in `TASKS.md`; mixed Day 2/3 items remain unchecked. No full-MVP or production-readiness claim is made.
