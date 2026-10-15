# SUT Reservation & Queue Management System

Day 1 + Day 2 implementation for a Taiwan-only internal coordination application: Python 3.12, FastAPI, synchronous SQLAlchemy 2, Alembic, SQLite, Jinja2 and locally served Bootstrap 5.3.8. Recorded status is advisory; the application never controls hardware, SSH, BMC or power.

Implemented: local accounts/RBAC, inventory/lifecycle management, atomic Claim/Release and Usage History, FIFO notification/manual Claim, reservations/check-in/no-show, pause/resume and inactive-user eligibility, and a background deadline processor. Browser forms, Calendar, My Usage, History and recipient-scoped in-app notices are available. **Full MVP is not complete:** Day 3 Dashboard action modals, notification bell/desktop opt-in and final acceptance remain. See [actual evidence](docs/implementation-status.md) and [Issue #2 verification](docs/day2-verification.md).

Read [AGENTS.md](AGENTS.md), [SPEC.md](SPEC.md), [PLAN.md](PLAN.md), [TASKS.md](TASKS.md), [SPRINT_3DAY.md](SPRINT_3DAY.md), [CODEX_START_PROMPT.md](CODEX_START_PROMPT.md) and [confirmed decisions](docs/decisions.md) before implementation. [Domain states](docs/domain-states.md) describe constraints and transaction boundaries.

## Local development

Run from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements-dev.txt
cp .env.example .env
# Edit .env: replace SECRET_KEY with a locally generated random value:
.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'
mkdir -p backend/data
cd backend
# Put .env here for native development (settings load .env in the working directory).
cp ../.env .env
export DATABASE_URL=sqlite:///./data/sut.db
../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.scripts.bootstrap_admin
../.venv/bin/python -m app.scripts.seed  # optional, APP_ENV=development only
../.venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

On Windows, use `.venv\Scripts\python`, `alembic` and `uvicorn`, create the directories using PowerShell and set `$env:DATABASE_URL`. Docker Desktop can use the local-build override below. Never copy production databases into development.

The bootstrap command securely prompts for credentials; it works only while no Super Admin exists. It never prints passwords and has no HTTP setup endpoint. Optional noninteractive inputs are `BOOTSTRAP_USERNAME`, `BOOTSTRAP_DISPLAY_NAME`, `BOOTSTRAP_TEAM`, `BOOTSTRAP_EMAIL`, `BOOTSTRAP_PASSWORD`; supply these through secure local process configuration, never command-line password arguments. Every admin-created account, including bootstrap, must replace its temporary password on first login. Password changes sign out **all** sessions; sign back in with the new password. The Super Admin supplies temporary passwords through a secure channel outside the app. There is no self-registration.

The development seed is repeatable and creates only two fictional labs and 20 fictional SUTs. It creates no users, credentials or real IP inventory. Do not run it in production.

## Authentication and API

Signed HttpOnly SameSite=Lax cookies carry an opaque session token. Only its SHA-256 digest is stored server-side; expiry, logout, password changes/resets and deactivation revoke authorization. Argon2id hashes passwords. Default minimum length is 12, maximum 128 (`MINIMUM_PASSWORD_LENGTH` can raise the minimum). Use a stable random `SECRET_KEY` of at least 32 characters. `COOKIE_SECURE=true` is the default; explicitly set false for trusted local/LAN HTTP, and use true behind HTTPS. Do not expose this application on the Internet.

Browser forms include CSRF fields. JSON clients first GET `/api/v1/auth/csrf`, retain the cookie, then send `X-CSRF-Token` for **every mutation**, including login/logout/password changes. Login rotates the CSRF token, so fetch a new one after login. Login accepts `username,password`; `/api/v1/auth/change-password` accepts `current_password,new_password`. Before mandatory password change, only authentication/logout/password-change functions are allowed. Twenty login attempts per client address per minute are permitted in the single-worker deployment; forwarded headers are not trusted by default.

`/health` is public liveness; the startup entrypoint runs migrations before listening. `/` redirects anonymous browsers to login. `/openapi.json` is authenticated and describes implemented JSON operations under `/api/v1`. Session and password fields are excluded from inventory/contact responses. API errors use `detail`; validation never reflects submitted passwords. Responses carrying application data use `Cache-Control: no-store`.

- Users view inventory/dashboard and edit their own display name, team and normalized unique work email at `/profile` or `GET/PATCH /api/v1/users/me`.
- Lab Admin and Super Admin manage **all** labs/SUTs. Names are manually entered and unique per Lab after trim/casefold, including archived names. Lab assignment cannot be changed. Nonempty labs cannot be deleted.
- SUT DELETE archives, blocked by usage, queue and current/future active reservations. Admins restore archived SUTs; ordinary inventory/KPIs exclude archives. No SUT hard-delete endpoint exists.
- Operational state is independent of recorded usage. Unavailable states require a reason and explicit acknowledgement if activity exists. Existing records remain, with affected users notified in persisted records. Queue offers pause with their remaining response time and resume after rechecking usage/reservation/account eligibility. New Claim/Queue/Reservation registrations are rejected while archived or unavailable; existing holders can Release or leave Queue and future bookings can be edited/cancelled.
- Super Admin alone provisions users, changes roles, resets passwords and disables/reactivates accounts. Preview `/api/v1/users/{id}/impact` or the account page first; acknowledge outstanding resources before disabling. `Needs attention` lists disabled users' unresolved resources. The final active Super Admin cannot be demoted or disabled, including concurrent attempts.

Dashboard defaults to Cards, with Table toggle, shared filters, natural Name/Status sorting, server-side booking summaries and 30-second read-only polling with stale/retry feedback. SUT Detail supplies Claim/Queue/Release/estimate forms, upcoming bookings and 30-second read-only status refresh that preserves unsaved input. Use Reservations, Calendar, My Usage, History and Inbox from the navbar. Dashboard quick-action modals and desktop alerts remain Day 3.

## Day 2 coordination contracts

All JSON routes are under `/api/v1`; see authenticated `/openapi.json` for typed payloads/responses. Browser forms use the same transaction services.

- `POST /suts/{id}/claim`: positive finite `duration_minutes` (fractional minutes are allowed to fit short bookings), optional `purpose`, optional `reservation_id`, `acknowledge_reservation_conflict`. Estimates have no business cap, but must fit a timestamp. One current usage per SUT; one user may hold multiple distinct SUTs. Reservation-specific Claim must fit within its booked end; invalid estimates are rejected, never silently shortened. Overdue use stays In Use until manual Release.
- `POST /suts/{id}/release` and `/force-release`: send the current **`usage_key`**. Force-release is admin-only and requires `reason`. The key protects a newer usage from stale retries. A successful release writes one history with actual interval, purpose, actor and reason, then removes the current usage atomically. A repeated/stale release returns 409 and never closes a replacement usage. A reservation-specific Release completes that booking, releasing its remaining priority; original booked times are retained.
- `PATCH /suts/{id}/usage/expected-end`: send `usage_key`, aware `expected_end_time`, and optional acknowledgement. Owner/admin only; the estimate must be after now/start. No Release/re-Claim or history mutation occurs. Claim/extension overlapping another booking returns 409 with `detail.code=reservation_conflict_confirmation_required`, booking/contact details and a suggested end. Review and explicitly resubmit with acknowledgement to keep the entered estimate. No reservation is shortened/cancelled.
- `GET/POST /suts/{id}/queue`: join with explicit positive `requested_duration_minutes`. As confirmed for Issue #2, an Available SUT with no queue must be Claimed directly; join only if In Use/Reserved or a queue already exists. Prevent duplicates and joining one's own active SUT. Order is `created_at,id`. Release notifies the first eligible member; notification **never creates usage**. Only the current notified eligible member may manually Claim; an active reservation owner has priority over FIFO and a successful reservation Claim removes their own queue entry.
- `DELETE /suts/{id}/queue`: send the current **`entry_key`** to leave one's own entry; stale retries cannot remove a rejoined entry. `DELETE /suts/{id}/queue/all` is admin-only, requires `reason`, audits explicit clearing across either lab and preserves usage/history/bookings. Queue `eligible` denotes active-account/operational eligibility; reservation priority, live offers and current usage are separately enforced by Claim.
- `GET/POST /reservations`, `GET/PUT/DELETE /reservations/{id}`: creation takes `sut_id,start_time,end_time,purpose`. Updates take start/end/purpose only; owner and SUT never transfer. Starts are strictly future and at most 30×24 hours ahead (inclusive), elapsed length is >0 and ≤24 hours. Active bookings use half-open `[start,end)` conflicts; adjacent windows are allowed. A usage estimate overlapping a new booking warns through `at_risk`, rather than preventing booking. Only owner/admin can edit/cancel future confirmed bookings. Cancellation retains the row, actor/time audit and re-evaluates queue eligibility.
- `POST /reservations/{id}/check-in`: reservation owner only, from start until **strictly before** start+15 minutes or booked end. Check-in records attendance (`waiting_for_release`) even while occupied/unavailable; it does not create usage. Notify the holder/admin to coordinate Release, then notify the checked-in owner to manually Claim. Priority persists until the booked end; checked-in users do not become no-show because a previous holder is late. Unchecked reservations become no-show at the 15-minute boundary. Bookings shorter than the grace period simply complete at their booked end if still unchecked.
- `GET /history` and `/reservations` support SUT/user/time filters and pagination (`page,page_size`, max 100). Time filters are aware instants in JSON and explicitly Asia/Taipei local inputs in HTML. History is retained indefinitely through archival/deactivation/profile edits. `GET /usages/me` and `/suts/{id}/coordination` expose minimal authenticated contact/status projections.
- `GET /notifications` is recipient-scoped and read-only; `POST /notifications/{id}/read` explicitly/idempotently marks one's own notice read. Inbox/Detail read-only polling never expires or marks anything read. No email/Teams/hardware action or automatic user-to-user transfer exists.

### Background deadlines and recovery

The FastAPI lifespan performs startup catch-up before accepting traffic and runs a periodic task (default `DEADLINE_POLL_SECONDS=1`, configurable 0.1–60 seconds). Production Compose keeps it enabled with **one Uvicorn worker**. Native tests may set `DEADLINE_PROCESSOR_ENABLED=false` to drive a frozen clock explicitly; do not disable production deadline processing without an equivalent managed worker.

Every sweep reserves SQLite with `BEGIN IMMEDIATE` before sampling the clock, and atomically commits reservation transitions, offer expiry/promotion, audits and uniquely keyed notifications. Repeated, restarted or overlapping sweeps cannot duplicate logical effects; an exception rolls back the whole sweep and the next bounded iteration retries. No browser or GET is required. The process does not release overdue usages. Mutation services recheck deadlines/priority under the same write reservation; a rejected request rolls back its transaction while the independent worker continues reconciliation.

A notified FIFO member has 15 minutes of **eligible response time**. Maintenance, active usage or reservation protection pauses the offer, retaining remaining microseconds and original queue order. Already-expired offers are processed before maintenance begins and are not resurrected. Restoring normal operation resumes remaining time only when priority allows. An inactive account's entry/booking remains for admin review; inactive entries are skipped for offers, and inactive reservation owners do not block allocation (retained bookings can still produce an overlap warning). Reactivating an earlier member cannot steal an already-issued live offer. Once that offer resolves, the earlier retained position resumes. Original booking/no-show wall-clock deadlines continue during maintenance.

Migration `b12d2c001001` adds stable usage/queue identities, resumable-offer fields and complete history metadata. Existing Day 1 records are backfilled without ownership/state changes. Back up the named volume before upgrades; the upgrade/backfill, downgrade/re-upgrade and database integrity are covered by tests. These are recordkeeping controls, not physical access controls.

## Validation

From repository root:

```bash
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
.venv/bin/pytest -q
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python scripts/browser_smoke.py
.venv/bin/python scripts/browser_day2.py
.venv/bin/python scripts/container_smoke.py
```

The browser smoke uses temporary migrated SQLite and generated synthetic credentials. It can use installed `chromium` or `CHROMIUM_PATH`. It exercises actual 30-second polling, layout/filter preservation, stale/retry feedback, login/first-password change and profile edits. The container smoke creates a randomly named Compose project, verifies port **5088**, migration, bootstrap/login, inventory and persistence across `down` then rebuild/recreate. Set `SUT_SMOKE_REMOTE_REF` to a published full application commit SHA to run it from a temporary directory containing only Compose/build settings, using the public GitHub remote context instead of local source. It also verifies real background no-show/offer processing without browser/GET activity, offline deadline catch-up and notification idempotency after restart. Synthetic test timeline updates are confined to that disposable volume; no debug timeline API exists. It removes **only its own disposable test volume**. Never use volume removal on deployment data. CI runs these checks; remote CI results must be inspected separately.

For a trusted corporate build proxy, the smoke accepts `SUT_BUILD_NETWORK=host` when required by the host, and `SUT_BUILD_CA=/path/to/approved/ca-bundle.pem`. It passes the CA as an optional BuildKit `build_ca` secret for pip trust **only during build**, and resolves inherited proxy hostnames for the builder. TLS and locked package-hash verification stay enabled. Do not install a private CA into the runtime image or disable verification. Ordinary builders need neither override. Production Compose can also supply an approved build CA via a local build-secrets override.

Runtime/dev dependencies are fully pinned with hashes in `backend/requirements*.txt`; edit `.in` manifests and regenerate with `uv pip compile --generate-hashes` when intentionally upgrading. Tests migrate isolated databases; startup never calls `create_all`. SQLite uses foreign keys, WAL and a five-second busy timeout. Writes reserve the database with `BEGIN IMMEDIATE` before checks. Contention returns retryable 503; deploy one app worker only.

## Linux production: Compose + public GitHub Remote Build

**Passing Day 1/2 checks is not full-MVP production acceptance.** A trusted Linux host needs Docker Engine, the Compose plugin, a Git-context-capable BuildKit builder and outbound access to public GitHub, Docker Hub and PyPI. No GitHub token is required for public source. Only `compose.yaml` and locally generated `.env` are needed on the host; no source checkout is needed. Dockerfile/source are fetched at build time, never at container startup.

1. Place `compose.yaml` on the host. Create `.env` locally with a random `SECRET_KEY`, `APP_PORT=5088`, a reviewed **full application commit SHA** for `SUT_GIT_REF`, `APP_BIND` set to the host's trusted LAN interface and `COOKIE_SECURE=false` only for trusted plain HTTP (true for HTTPS).
2. Restrict inbound TCP 5088 to trusted LAN clients using host/network firewall rules. Default binding is loopback; set the intended LAN interface explicitly. Public source is not authorization to expose runtime data publicly.
3. Start, inspect and bootstrap:

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail=100
curl --fail http://127.0.0.1:5088/health # use the configured APP_BIND if not loopback
docker compose exec sut-management python -m app.scripts.bootstrap_admin
```

Open the configured LAN address on port 5088, sign in and change the temporary password. Verify from two LAN browsers on the real host. Actual host/firewall/LAN reachability cannot be established by agent-local checks. In-app HTTP features do not require browser desktop-notification permission. Opt-in desktop alerts may require a trusted HTTPS internal hostname; private-IP HTTP is usually not a secure context and must retain in-app fallback.

DEP-006 mapping is **Host TCP 5088 → Container TCP 80** (`5088:80`). Uvicorn listens on `0.0.0.0:80`; Docker `EXPOSE` and the in-container healthcheck also use port 80. `APP_PORT` changes the host port only.

The image remains UID/GID **10001:10001**, with `cap_drop: ALL` and `no-new-privileges`. Compose explicitly sets **`net.ipv4.ip_unprivileged_port_start=80` in the container's own network namespace**. This allows the non-root listener on port 80 while keeping ports 1–79 privileged; no `NET_BIND_SERVICE`, root startup, Python file capability or host-wide sysctl change is required. Keep the private bridge network; do not replace it with host networking. A manual `docker run` on a stricter engine must supply the same container-local `--sysctl net.ipv4.ip_unprivileged_port_start=80`. The native virtualenv command above uses local development port 8000 and is separate from the container contract.

When upgrading from Day 1/2, replace the host's `compose.yaml` with the reviewed DEP-006 revision **and** update `SUT_GIT_REF`, then recreate the service. The browser URL stays on host 5088 and the existing SQLite volume is retained; this port change needs no database migration. Rolling back to a pre-DEP-006 image also requires its matching Compose mapping (those historical images listened on 8000). Never mix an old image with the new port-80 mapping or remove the volume during this update.

SQLite lives at `/app/data/sut.db` in the `sut-data` named volume, owned by runtime UID/GID 10001. A fresh volume inherits image directory ownership; for a restored volume preserve that ownership. The non-root image runs migration-before-startup and a single Uvicorn worker. Missing/invalid secrets or failed migration prevent serving. Production accounts, emails, IP inventory, hashes, schedules and histories stay in this volume; they never enter Git or the image.

For a local Docker build with checked-out source:

```bash
# .env still supplies SECRET_KEY and SUT_GIT_REF; the latter is overridden as build context.
docker compose -f compose.yaml -f compose.local.yaml up -d --build
```

GitHub pushes do not automatically redeploy. Back up first, update `SUT_GIT_REF` to the reviewed new SHA, then explicitly run `docker compose up -d --build`. Confirm logs, health and login. Normal `docker compose down` retains the named volume. **Never use `docker compose down -v` for routine maintenance.** Rollback to the prior image/ref only with a compatible schema or a tested pre-upgrade database restore.

## Backup and restore

Indefinite history retention is an application policy, not a backup guarantee. Schedule encrypted off-host backups and periodically test restores. For a consistent backup, stop the web service (so no writer is active) and copy the **entire** data directory, including any SQLite WAL/SHM files, using a temporary container mounted on the same volume:

```bash
mkdir -p backups
chmod 700 backups
docker compose stop sut-management
docker compose run --rm --no-deps --entrypoint sh -T sut-management -c 'tar -C /app/data -cf - .' > backups/sut-data.tar
docker compose start sut-management
```

Protect the resulting archive; it contains credentials and internal data. For restore, stop the service, retain a recovery copy of current data, restore the entire backup into an **empty** compatible volume, preserve ownership 10001:10001, and start the matching application revision. Check SQLite `PRAGMA integrity_check`, migration version, health, login and representative inventory/history. Do not overlay a backup onto live database/WAL files or silently downgrade a migrated database. A deployment-specific backup/restore rehearsal is still required.

## Day 3 Dashboard and notifications

Both Dashboard layouts offer Claim, Queue, Reserve and Detail modals. Duration presets or positive custom minutes support multi-day estimates; queue duration remains an integer. Dates explicitly represent Asia/Taipei regardless of browser timezone. Conflict acknowledgement never shortens the estimate. Server-side services remain authoritative for stale state, FIFO/reservation priority, maintenance, roles and concurrent submissions. Successful actions close the modal and refresh the shared Dashboard; filters/layout/scroll and other unsaved inputs are preserved. Full SUT Detail provides Release, estimate edits, check-in links and administrator operations.

The bell shows the recipient's total unread count, with a recent-notice preview and complete paginated Inbox history. `GET /api/v1/notifications` accepts `page`, `page_size` (1–100), `after_id` and `through_id`; returns `items,total,unread_count,latest_id`. The count covers all retained notices, independently of the page. Bounded ID polling avoids shifting pages while new notices arrive. Only explicit CSRF-protected `POST /api/v1/notifications/{id}/read` marks a recipient's own notice read. Schedule confirmation, reservation start, queue/expiry, overdue and maintenance notices are persisted; repeated deadline sweeps do not duplicate them.

Desktop alerts require a supported secure context (HTTPS or localhost), browser/OS permission and an explicit **Enable desktop notifications** click. Private-IP HTTP normally falls back to Inbox. Permission is never requested on login/page load. Alerts work best-effort while the site is open; there is no service worker or delivery guarantee after closing the site. IDs are deduplicated between polls and a tab's reloads; independent tabs may each alert. Desktop bodies are generic and omit colleague emails/purposes. If storage or desktop delivery is unavailable, in-app history remains authoritative.

Run `.venv/bin/python scripts/browser_day3.py` for modal/layout/keyboard/mobile/notification acceptance. `scripts/container_smoke.py` now includes a cold backup restored into a separate empty disposable named volume, validating sessions/history/notices/schema/integrity. Production backup recovery must still be rehearsed on the actual host.

Windows development may use Docker Desktop with Linux containers and `docker compose -f compose.yaml -f compose.local.yaml up -d --build` from the checkout (PowerShell environment variables or a host-only `.env`). Production continues to use the pinned public GitHub Remote Build path on Linux; no GitHub push automatically updates a running server.
