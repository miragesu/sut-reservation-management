# Codex Implementation Plan — SUT Reservation & Queue Management System

Version: 1.4-draft | Execution strategy: small verified pull requests

## Ground rules
Read `SPEC.md`, `AGENTS.md`, `TASKS.md` before coding. Stop and ask when a requirement marked `DECISION` is unresolved and implementation would lock in a policy. Do not implement future enhancements. Each phase ends with passing tests, updated docs, and a runnable application. Create one PR per phase or independently testable slice. Never claim commands were executed unless they were run.

## Phase 0 — Requirement freeze & decisions
**Goal:** turn proposed policy into confirmed business rules.
- Review and resolve the eight open decisions in `SPEC.md` §11.
- Write accepted choices to `docs/decisions.md` and update the SPEC to remove the corresponding `DECISION` tags.
- Confirm MVP exclusions and simple UX wireframes.
**Gate:** No contradictory queue, claim, reservation and deletion semantics remain.

## Queue handoff policy
BR-004 is confirmed: notification-first FIFO handoff, followed by manual Claim. BR-005 is confirmed: a notified queue head has 15 minutes to Claim; otherwise expire the offer, audit the timeout, notify the user and the next eligible waiting user. Preserve reservation priority, restart safety, and race-safe transactional Claim/expiry. No hardware-level control.

## BR-008 — Lab Admin scope (confirmed)
Lab Admin may manage both Taiwan labs and all SUTs (including Lab/SUT CRUD, recorded force-release, and queue clearing). No lab-assignment mapping table or lab-specific RBAC. Only Super Admin manages users/roles/system configuration. Test each operation across both labs.

## BR-009 — SUT archival policy (confirmed)
Treat SUT DELETE as reversible archive, never physical deletion. Add archive fields and audited admin restore. Reject archival while a SUT is recorded as in use, actively queued, or has ongoing/future active reservations (409); do not auto-cancel them. Hide archives from default active inventory/KPIs and prohibit new Claim/Queue/Reservation on archived SUTs. Preserve all history and test archive/restore access, consistency and filter behavior.

**BR-020 confirmed (Phase 1):** Super Admin-only account creation; no public registration. Implement secure initial administrator bootstrap CLI, admin account creation and temporary password reset, `must_change_password` flag, forced password-update flow before normal protected pages/APIs, and audit without secrets. Test first login, unauthorized create/reset, password rules and recovery. Do not build self-registration, email invites or Teams onboarding.

## Phase 1 — Runnable scaffold & auth
**Goal:** boot an authenticated FastAPI web app with Alembic and Docker.
- Create repo structure, pinned/ranged compatible dependencies, settings, logging, health endpoint.
- Create SQLAlchemy base, unit-of-work/session dependency, Alembic migration setup and all schema tables.
- Create Bootstrap/Jinja2 base template, login/logout pages, session + CSRF security and permission dependencies.
- Create first-admin CLI without default credential and dev-only seed command.
- Add Dockerfile, compose, volume, `.env.example`, README, pytest fixtures, CI workflow.
**Gate:** Compose boots; fresh migration completes; admin can log in; `/health`=200; tests run; no secrets committed.

## Phase 2 — Lab & SUT inventory
**Goal:** secure inventory CRUD and dashboard visibility.
- Implement Lab CRUD and all-lab role-based admin access (BR-008), with no lab assignments; SUT CRUD/deletion/archive rules.
- Implement dashboard KPI counts with derived effective status, SUT listing/filtering/pagination, detail basic info.
- Implement matching REST endpoints and HTML forms using shared services.
**Gate:** Admin and standard user access checks, deletion constraints, unique fields, search and totals tested.

## Phase 3 — Claim, release, FIFO queue & history
**Goal:** safe exclusive allocation with complete auditability.
- Implement claim duration validation, active usage creation and transaction serialization.
- Implement release/force-release and idempotency-safe history writing.
- Implement queue join/leave/clear, derived position, strict FIFO notification-first offer on release; notified queue head must manually Claim. Add 15-minute offer deadlines, a periodic retry-safe timeout worker, audited expiry, re-queue-at-tail behavior, in-app notifications, and automatic notification of the next eligible FIFO user (respecting reservations).
- Implement usage history filtering and overdue visual indicator.
**Gate:** Concurrent double-claim tests pass; FIFO order, 15-minute boundary, worker restart/idempotency, concurrent Claim vs offer expiry, reservation-blocked promotion, own-only release, force release audit and history integrity tested.

## Phase 4 — Reservations & calendar
**Goal:** reservation-aware status, check-in and notifications integrated with claims and queues; not hardware enforcement.
- Implement create/list/cancel and overlap/conflict checks.
- Integrate reservation checks into claim and promotion (transactional revalidation), allowing temporary use before upcoming bookings with prominent warnings and suggested handoff times (no hardware cutoff).
- Implement a periodic single-instance no-show sweeper for unclaimed reservations at start + 15 minutes; audit transition, revoke reservation protection, and retry FIFO notification-first offer atomically if free.
- Add calendar views and Asia/Taipei display/input behavior with UTC at rest.
- Display reserved/in-use/available states consistently across dashboard/list/detail.
**Gate:** Boundary intervals `[start,end)` tests, overlapping bookings, cross-timezone conversions, reservation-owner claim, temporary queue allocation, timely no-show expiration, checked-in-but-occupied handoff with manual confirmation, in-app warnings, and double-record prevention all pass.

## Phase 5 — Hardening, handoff & release
**Goal:** deliver repeatable, reviewable MVP.
- Add E2E smoke path from login to reservation/claim/queue/release/history.
- Validate migrations on fresh volume, data persistence after container recreation, HTML security, API error contract, accessibility basics.
- Reconcile spec vs implementation; update README/CHANGELOG; record known limitations.
**Gate:** All acceptance criteria in `SPEC.md` §10 and `TASKS.md` checked with evidence (commands/results, screenshots only when helpful).

## PR delivery template
Every PR description must include: scope, user-visible change, migrations, API changes, tests executed with results, manual QA steps, known limitations and open decisions. Avoid a single massive PR with all features.

## Initial Codex task prompt
> Read `AGENTS.md`, `SPEC.md`, `PLAN.md`, and `TASKS.md` in full. Begin at Phase 0. Report unresolved policy decisions; do not invent product rules. After decisions are confirmed, implement only the next unchecked phase. Keep HTML and API routes thin and place shared business logic in services. Implement tests, execute them, update documentation and mark only verified tasks completed. Deliver changes as a focused pull request with a concise validation report.

## BR-007 implementation note (confirmed)
Phase 3 must permit the same user to Claim two different SUTs and independently Release each one. Add tests confirming per-SUT exclusivity without imposing a per-user ownership limit.

## BR-010 Naming validation gate (confirmed)
During SUT inventory implementation, the admin manually enters a SUT name; enforce case-insensitive, trimmed unique names per Lab at the database level (including archived SUTs). Different Labs may reuse names. Tests must cover duplicate creation, rename, archive, cross-Lab names and concurrent insertion.

## Confirmed implementation note — BR-011

For Phase 3 Claim and history, accept positive custom durations without an 8-hour business maximum, including multi-day estimates. Preserve the current usage after `expected_end_time`; annotate overdue status and provide in-app reminders without automatic release or device controls. Test actual release duration separately from the estimate. **BR-012 confirmed:** each reservation has a 24-hour maximum elapsed duration; test 24h accepted, >24h rejected, and nonpositive duration rejected across API/UI. **BR-013 confirmed:** allow future reservation start instants up to and including now + 30 × 24 hours; reject starts beyond the horizon on both API/UI. Compare UTC instants; display Asia/Taipei; test inclusive 30-day boundary, just over 30 days, past starts, and duration independent of horizon.

**BR-014 confirmed:** implement owner/admin update (PUT) and cancellation (DELETE) for future `confirmed` reservations in Phase 4. Re-run 24h, 30-day-from-edit, overlap and state checks transactionally; preserve cancellation and before/after edit audit; prevent editing started/claimed/checked-in bookings. Test owner, unrelated user, Lab Admin, Super Admin and race conflicts.

## Confirmed BR-015 — Adjust active usage estimates
Phase 3: add PATCH `/api/v1/suts/{id}/usage/expected-end`, shared service logic and SUT detail edit UI. Restrict to current owner or admin, show reservation conflicts and require explicit acknowledgement. Keep the same active usage, never trigger Release/Claim, preserve audit history; add API/UI tests for normal extension, overlapping reservations, refusal without acknowledgement, forbidden user, expired usage estimate, and no device access control.

## Confirmed BR-016 — Release then manual Claim (Phase 3)
- Do not implement a direct user-to-user handover or reassignment feature in MVP.
- Reuse existing Release/Claim workflows. On Release, apply checked-in reservation priority or Queue FIFO notification with BR-005 timeout; next user manually Claims before appearing In Use.
- Preserve separate usage history records, auditable actor/timestamps, and non-hardware-control MVP scope. Test attempted bypass of queue/reservation priority.


### BR-017 implementation addition (confirmed)
In the SUT management phase, add operational state fields + Alembic migration (`normal`, `maintenance`, `out_of_service`), admin status-update route/form, audit, and consistent status badges. In the Queue/Reservation phase, gate *new* app actions on operational state, preserve and warn for existing activity, pause/resume queue notifications safely, and test interactions with active usage and checked-in reservations. No device-side control.


### BR-018 — 30-second HTTP polling (confirmed)
In Phase 2 implement read-only, authenticated status polling on Dashboard and SUT Detail; extend it in the notification/Queue phase to unread in-app notifications and reservation state. Use a configurable 30,000 ms interval (MVP default), lightweight JSON endpoint(s), client DOM updates without destroying filters or form input, immediate refresh after successful mutations, and visible retry/stale state on network errors. The server remains the only authority for state transitions/expiry; never trigger mutation via GET/polling. Test changed state appearance, authorization, error/retry, duplicate-notification avoidance, and no mutation from polls. WebSocket/SSE are out of MVP scope.


## Confirmed BR-019 implementation note — Notification channels

Implement in-app notification persistence, recipient-scoped read/unread APIs, a notification bell/list, and 30-second read-only polling as part of the Queue/Reservation notification phase. Add an explicit user-click `Enable desktop notifications` control backed by the browser Notification API; send optional desktop alerts only while the website is open, deduplicated per notification ID. Handle denied/unavailable permission without breaking the site. Do not implement SMTP, Teams, push subscriptions or service workers for MVP; keep Email/Teams in the future roadmap. Add server and browser tests for permissions, recipient isolation, idempotency and duplicate prevention.

### BR-021 — User deactivation and outstanding resources (confirmed)
In Phase 1 user management, add Super Admin-only account activate/deactivate action, audited timestamps/actor/reason, immediate rejection of disabled users' existing sessions, and a guard against disabling the last active Super Admin. Provide preview of current usages, queues and upcoming reservations plus a persistent Admin `Needs attention` panel. Do **not** automatically Release, leave Queue, cancel bookings or touch hardware. In Phase 3 Queue worker skip ineligible inactive accounts without deleting underlying records or blocking FIFO progression; in Phase 4 preserve reservation lifecycle and expose unresolved items for admin follow-up. Add end-to-end role/session/impact/record-integrity tests.


## BR-022 — Coordination visibility (confirmed)
Implement user team and optional active-usage purpose migrations, include work email/team in authenticated SUT detail/queue/reservation pages and relevant API projections. Protect anonymous access, keep sensitive fields excluded, and test cross-user visibility plus privacy boundaries.

### BR-023 — User profile self-service (Confirmed; Phase 1/auth + UI)
Implement `/profile` page and authenticated `GET/PATCH /api/v1/users/me` allowing current user to edit display name, team and unique work email; use existing `/api/v1/auth/change-password` for self-service password updates. Add server-side allowlist and validation, duplicate-email handling, CSRF-protected forms, audit and security tests. Preserve username, role, account flags and immutable history attribution; enforce first-login password-change gate. Verify refreshed contact details appear in coordination views (BR-022).


### BR-024 — Permanent-by-policy Usage History (Confirmed)
During the usage/history implementation phase, ensure released and admin-closed usages produce exactly one durable history record, retain histories on SUT archive and user deactivation, and provide filter/pagination APIs/UI without destructive effects. Review foreign keys and ORM cascades to prevent accidental deletion; do not build history TTL/purge cron/API for MVP. Verify preservation with integration tests. Document regular SQLite backups as an operational recommendation (not automatic deletion).

## BR-025 implementation note — dashboard layout toggle (confirmed)
In Phase 2 implement Dashboard with Card view as default plus Table view using the same server-provided SUT dataset, status calculation, search and filters. A small vanilla JavaScript/Bootstrap accessible toggle is sufficient; do not introduce a SPA framework. In the existing Phase 2/BR-018 polling work, update KPI counts and the active view every 30 seconds while retaining the selected view and filter state. Add tests for equivalent results in both layouts and for polling without resetting the UI.


## BR-026 implementation note — reservation summaries by Dashboard layout
In the Dashboard phase, keep one SUT/filter/status query source but add two reservation projections: Card view uses the nearest upcoming valid reservation for each SUT; Table view lists every valid reservation overlapping the rolling `now` to `now + 24h` window for each SUT. Query on server UTC timestamps; format in Asia/Taipei. Avoid one DB query per SUT (batch load reservations for approximately 20 devices). Ensure the 30-second polling endpoint returns refreshed summaries and never resets view/filter state. Add boundary, exclusion, and view-switch tests.

## BR-027 implementation note — Dashboard quick-action modals (confirmed)
During Dashboard/UI phase, add shared Bootstrap modal components for Claim, Join Queue and Reserve accessible in both Card and Table views. Route their submissions through existing authenticated services/endpoints (not parallel business logic). Include server-side race-safe permission/state validation, conflict warnings, failure states and duplicate-submit protection. After success refresh the active dashboard view and metrics immediately; preserve BR-025 view/filters, BR-026 per-mode reservation summaries, and BR-018 30-second polling without disrupting open forms. Test keyboard accessibility, both modes, invalid inputs and concurrent submissions.


## BR-028 — Dashboard sorting (confirmed)
Implement Name (default, natural ascending) and Status as the ONLY user-facing sort choices in Card/Table modes, sorting inside each Lab. Use one shared query/projection and preserve selected sort through view toggle, filtering, and BR-018 polling. Include stable tie-breaking and tests. See `SPEC.md` BR-028.

## Three-day execution constraint
See `SPRINT_3DAY.md`. Three days is a **timebox and evidence-based checkpoint**, not a guarantee that the entire v1.0 scope can be production-ready. Prioritize working vertical slices and passing tests; do not silently remove confirmed BR requirements. Deferred or incomplete items must be explicit in the PR and TASKS.md.

## Full-MVP target supersedes earlier beta sprint proposal
The confirmed execution objective is **Option A: all BR-001–BR-028**, with a three-day target and automatic extension when required. `SPRINT_3DAY.md` now gives the current chronological dependency plan. Any older wording describing a three-day beta or allowing P1 spillover is superseded for delivery scope; incomplete confirmed BRs BLOCK MVP acceptance. See `CODEX_START_PROMPT.md` for Codex kickoff.

## DEP-001 — Deployment critical path
Implement Compose port mapping, persistent database and documented one-host deployment on Day 1, not as an afterthought. Re-run deployed-port smoke checks and restart persistence on Day 3. All environment-specific routing/firewall checks on `10.88.26.99` require server-side validation. See SPEC.md DEP-001.


## DEP-002 — Remote Build implementation critical path
Day 1: add production `compose.yaml` using pinned GitHub remote build context and root `Dockerfile`, with `5088:80`, migrations, health, and named SQLite volume. Keep Windows development with local build override as needed. Day 3: verify on Linux with only Compose + local secrets (no app checkout), including rebuild/restart persistence, update/rollback guide, and private-repo authentication instructions if applicable. See SPEC.md DEP-002.

## DEP-004 — Public GitHub decision and delivery gates

Codex must implement production GitHub remote build against a **public** source repository; remove private-repo authentication from the MVP's critical path. Day 1: add safe `.gitignore`, `.dockerignore`, `.env.example` and no-secret seed data, plus a pinned-ref production Compose example. Day 3: validate clean-public-tree checks, LAN-only service exposure, remote build without credentials, migration, persistence, and rollback. Never push production SUT IP inventory, user accounts, or SQLite databases to GitHub.

## DEP-007 — Docker Hub image deployment supersedes the primary Remote Build path
Confirmed by Issue #6: release tested Linux amd64 images to `mirage315/sut-reservation-management` on explicit `v*` version tags only. Use scoped GitHub Actions secrets `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`, full-SHA pinned actions and successful automated checks before publishing; record version/source/digest provenance and verify an anonymous published-digest pull. Production administrators use image-only `compose.deploy.yaml` with a version/digest (never default latest), a securely supplied persistent SECRET_KEY, no source checkout/build. Keep 5088:80, non-root UID 10001, all capabilities dropped, no-new-privileges, private-network port-80 sysctl, Alembic startup and named SQLite volume. GitHub Remote Build remains optional for developers. Preserve the existing project/volume when switching deployment files; back up before schema upgrades and do not assume an old image supports a newer database. Do not claim registry publication, a separate-server deployment or LAN acceptance without actual evidence. See docs/deployment.md and docs/dep007-verification.md.


## DEP-008 — Administrator deployment / bind storage (confirmed)
The project owner's DEP-008 request supersedes Named Volume requirements **only for the primary image-only production deployment**. `compose.deploy.yaml` uses long-form bind `/data/sut-reservation-data` → `/app/data`, with `create_host_path: false`; operators verify the persistent `/data` mount and prepare UID/GID 10001 ownership/mode 700. Existing Named Volumes must not be deleted or migrated automatically. The optional Remote Build path and disposable recovery test volumes remain Named Volumes. Preserve the published v1.0.0 image, application code, 5088:80, non-root/security/deadline/migration behavior. See docs/deployment.md for reviewed Compose selection, secure local configuration, cold backup/empty-directory restore, upgrade and manual migration. Actual production/LAN validation remains external.


## DEP-009 — Single-script setup, password policy and version selection (confirmed Issue #9)
Operator setup is the reviewed root `setup.sh` with pinned/checksummed Compose, no source build or host Python. Preserve the DEP-008 bind path, 5088:80, UID10001, all capabilities dropped, no-new-privileges, private port80 sysctl, Alembic and background deadlines. Verify actual /data mount/disk/boot ordering; never migrate/delete old volumes or silently recreate existing data. Retain private .env/SECRET_KEY and image digest lock on reruns; upgrades require explicit version selection, cold backup and post-upgrade health/migration/record verification. No automatic schema downgrade.
`LOW_SECURITY_PASSWD` defaults false; only explicit true/false are valid. Default minimum 12 (existing configurable higher minimum retained), low mode minimum 1, maximum 128; reject empty/whitespace-only, no composition rules. Apply to all roles/provision/reset/change/bootstrap and HTML/API. Keep Argon2id, CSRF, rate limits, RBAC, session revocation and mandatory first-login change; SECRET_KEY remains random 32+. Warn/confirm the substantially increased access risk. Published1.0.0 does not support the new mode.
Primary Compose image is `mirage315/sut-reservation-management:${SUT_VERSION:-stable}`; operator chooses stable/latest/explicit version, installer records actual immutable digest internally. Missing preferred aliases may offer verified1.0.0 only with confirmation; network failures or missing explicit versions stop. No running container automatically follows alias changes. Official version publishing rejects existing explicit tags; latest promotion follows published-digest deployment success, stable additionally requires explicit workflow dispatch and protected environment approval/configuration. Do not publish/overwrite1.0.0 or new images in this development task. Tentative1.0.1 requires reviewed merge and a separately authorized new release. See docs/deployment.md and docs/implementation-status.md for actual verification/external gates.
