# SUT Reservation & Queue Management System

Day 1 foundation for a Taiwan-only internal coordination application: Python 3.12, FastAPI, synchronous SQLAlchemy 2, Alembic, SQLite, Jinja2 and locally served Bootstrap 5.3.8. Recorded status is advisory; the application never controls hardware, SSH, BMC or power.

Implemented: local accounts, roles, mandatory first-password change, profile/password management, account deactivation with outstanding-resource review, Lab/SUT management, archive/restore, administrative maintenance states, initial Dashboard and automated tests. **Full MVP is not complete.** Claim/Release, queue/reservation services and deadline processing are Day 2; complete notification/action UI is Day 3. See [actual evidence and limitations](docs/implementation-status.md).

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
- Operational state is independent of recorded usage. Unavailable states require a reason and explicit acknowledgement if activity exists. Existing records remain, with affected users notified in persisted records. Queue pause/resume and new coordination-action guards will be completed with Day 2 services; those endpoints are not exposed yet.
- Super Admin alone provisions users, changes roles, resets passwords and disables/reactivates accounts. Preview `/api/v1/users/{id}/impact` or the account page first; acknowledge outstanding resources before disabling. `Needs attention` lists disabled users' unresolved resources. The final active Super Admin cannot be demoted or disabled, including concurrent attempts.

Dashboard defaults to Cards, with Table toggle, shared filters, natural Name/Status sorting, server-side booking summaries and 30-second read-only polling with stale/retry feedback. No Claim/Queue/Reserve action is advertised until its service exists. SUT Detail automatic refresh and complete notification UI remain outstanding.

## Validation

From repository root:

```bash
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
.venv/bin/pytest -q
.venv/bin/python -m playwright install --with-deps chromium
.venv/bin/python scripts/browser_smoke.py
.venv/bin/python scripts/container_smoke.py
```

The browser smoke uses temporary migrated SQLite and generated synthetic credentials. It can use installed `chromium` or `CHROMIUM_PATH`. It exercises actual 30-second polling, layout/filter preservation, stale/retry feedback, login/first-password change and profile edits. The container smoke creates a randomly named Compose project, verifies port **5088**, migration, bootstrap/login, inventory and persistence across `down` then rebuild/recreate. Set `SUT_SMOKE_REMOTE_REF` to a published full application commit SHA to run it from a temporary directory containing only Compose/build settings, using the public GitHub remote context instead of local source. It removes **only its own disposable test volume**. Never use volume removal on deployment data. CI runs these checks; remote CI results must be inspected separately.

For a trusted corporate build proxy, the smoke accepts `SUT_BUILD_NETWORK=host` when required by the host, and `SUT_BUILD_CA=/path/to/approved/ca-bundle.pem`. It passes the CA as an optional BuildKit `build_ca` secret for pip trust **only during build**, and resolves inherited proxy hostnames for the builder. TLS and locked package-hash verification stay enabled. Do not install a private CA into the runtime image or disable verification. Ordinary builders need neither override. Production Compose can also supply an approved build CA via a local build-secrets override.

Runtime/dev dependencies are fully pinned with hashes in `backend/requirements*.txt`; edit `.in` manifests and regenerate with `uv pip compile --generate-hashes` when intentionally upgrading. Tests migrate isolated databases; startup never calls `create_all`. SQLite uses foreign keys, WAL and a five-second busy timeout. Writes reserve the database with `BEGIN IMMEDIATE` before checks. Contention returns retryable 503; deploy one app worker only.

## Linux production: Compose + public GitHub Remote Build

**Day 1 is not full-MVP production acceptance.** A trusted Linux host needs Docker Engine, the Compose plugin, a Git-context-capable BuildKit builder and outbound access to public GitHub, Docker Hub and PyPI. No GitHub token is required for public source. Only `compose.yaml` and locally generated `.env` are needed on the host; no source checkout is needed. Dockerfile/source are fetched at build time, never at container startup.

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

Open the configured LAN address on port 5088, sign in and change the temporary password. Verify from two LAN browsers on the real host. Actual host/firewall/LAN reachability cannot be established by agent-local checks. In-app HTTP features do not require browser desktop-notification permission. Future opt-in desktop alerts may require a trusted HTTPS internal hostname; private-IP HTTP is usually not a secure context and must retain in-app fallback.

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
