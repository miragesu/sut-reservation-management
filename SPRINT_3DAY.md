# Three-Day Full-MVP Codex Execution Plan (Option A)

**Goal:** Implement and verify **all confirmed BR-001 through BR-028**, not a reduced beta. The three-day window is an **aggressive target, not a waiver of acceptance criteria**. If any required behavior or critical test fails after Day 3, continue development; report remaining work and do not declare MVP complete.

## Source-of-truth priority
1. `docs/decisions.md` for confirmed decisions (latest supersedes old proposals)
2. `SPEC.md` for functional behavior and data/contracts
3. `SPRINT_3DAY.md` for implementation sequence (not scope reduction)
4. `TASKS.md` for acceptance evidence
5. `AGENTS.md` for process and technical guardrails

If conflicting rules appear, document the conflict and propose the smallest consistent interpretation. Do not implement silent assumptions affecting reservation/queue priority. Never confuse DB status with physical SUT access control.

## Preconditions / feasibility
- A working Codex environment, repo permissions, Python/Docker access and frequent human review are assumed.
- No guarantee that a single unattended coding-agent run finishes in 72 hours. Work in reviewable commits/PRs with repeated execution and feedback.
- Three days means three concentrated workdays. Do not sacrifice security, migration correctness or concurrency correctness to meet schedule.

## Priority order (all are MVP requirements)
**Critical path:** (1) schema/state machines/constraints and auth; (2) Claim/Release/history; (3) reservation check-in/no-show and queue offers including deadline processing and priority; (4) dashboard + notifications/UI; (5) full edge-case/security/integration verification. Functional order != permission to defer anything.

## Day 1 — Foundation, auth and inventory (target: fully passing vertical slice)
- Set up reproducible Python 3.12 FastAPI + SQLAlchemy 2 + Pydantic v2 + Alembic + SQLite + Jinja2 + Bootstrap 5 + Compose.
- Write domain model/state transition tables FIRST for users, labs, SUTs (including lifecycle status), usages/history, queues/offers, reservations/check-ins, notifications, audit logs. Model UTC storage and Asia/Taipei UI. Include transaction constraints and indexes.
- Build login/session/CSRF, Super Admin one-time secure bootstrap, admin-provisioned accounts, forced first-password change, roles scoped as BR-008, self-profile edit, deactivate/reactivate and resource-review list (BR-020–023).
- Implement Lab/SUT create/edit, unique normalized name within a Lab including archives, archive/restore with guards, maintenance/out-of-service (BR-009/010/017), tests.
- **Gate 1:** fresh migrations; secure auth/access checks; role tests; inventory/UI CRUD, no data loss, Compose launch and persistence all pass.

## Day 2 — Complete coordination engine (hardest work first)
- Implement atomic per-SUT Claim/Release and usage history, multi-SUT use, expected end extension with booking warning+acknowledgement, overdue indication, manual handover via Release then Claim (BR-001/011/015/016/024).
- Implement Queue FIFO, notify first and wait for manual Claim, 15-minute offer expiry/next eligible, no duplicates, leave/clear (BR-004/005). Ensure disabled users/maintenance/checked-in reservations cannot deadlock the queue.
- Implement reservations (start future ≤30 days, duration >0 and ≤24h, no overlap), edits/cancels, calendar, check-in by +15 minutes, no-show at deadline, checked-in waiting-for-release priority, warnings/temporary use (BR-002/003/012/013/014).
- Build **reliable idempotent deadline processor** that works without browser visits and has startup/restart reconciliation; ensure single effective expiration/notification even with multiple web workers. Use a documented single-scheduler deployment or separate worker design for SQLite.
- **Gate 2:** run deterministic frozen-clock tests, transactions/competing Claims, boundary cases at exact 15m, no-show vs check-in, queue rollover, overlap, restart recovery, and API authorization. No second active usage per SUT.

## Day 3 — Dashboard, notifications, full verification and handoff
- Dashboard card default/table toggle; card next reservation; table rolling next 24h; search/filter; Name default/Status sort (only those two, within lab); 30s HTTP polling preserving local UI/modals; quick Claim/Queue/Reserve modals (BR-018/025–028).
- In-app read/unread/deduplicated notices and optional permission-based desktop notifications when website is open; no email/Teams in MVP (BR-019). Display names/team/work-email/purpose for logged-in users (BR-022).
- Finish Calendar, History, Admin screens and all outstanding CRUD/role/notification/test cases. Verify audit, archived SUT history, deactivated account obligations, maintenance state, security and error pages.
- Run fresh `alembic upgrade head`, `pytest`, Docker Compose build/up, restart persistence, browser-based manual scenario walkthrough for both labs and representative 20 SUTs.
- **Gate 3:** every MUST and BR-001–028 test passes; no critical/high issues; documented admin bootstrap, configuration, run, migration, backup and restore; every task checked with evidence.

## Daily execution loop
1. Read specification and outstanding tests; choose one narrowly scoped vertical slice.
2. Implement migration, service, API/HTML, tests together; run tests and lints; commit with BR refs.
3. Review diff and capture commands/results; log defects and known gaps in `docs/implementation-status.md`.
4. Recompute remaining hours; prioritize highest integration risk first. Do not cut confirmed scope without explicit user decision.

## Acceptance and stop conditions
**PASS / Full MVP:** all BR-001–BR-028 and security/migration/Compose criteria verified with recorded evidence. Only then call it delivered. **NOT DONE:** any incomplete BR, failed test, unresolved data-corruption/auth/concurrency defect, or unverified deployment. After Day 3 continue by risk until PASS; elapsed time alone never converts NOT DONE to PASS.

## Explicitly out of scope
Controlling or locking physical SUT access; automatic release of overdue usage; Microsoft Entra ID, Email, Teams, Redfish/IPMI; other-country labs; a new frontend SPA stack.

## DEP-001 — Three-day deployment checkpoints
- **Day 1:** Docker image builds from entire repo; Compose publishes 5088:80, data volume persists, migration and /health work; document GitHub remote-context Compose deployment, production secrets and bootstrap.
- **Day 2:** Verify queue and reservation timeout processor survives worker/container restart without duplicate notifications.
- **Day 3:** Rebuild/restart/backup/restore smoke checks, LAN browser access validation on actual host when available, desktop notification fallback over plain HTTP; unresolved host firewall/DNS conditions reported distinctly from application test results.



## DEP-002 remote build checkpoints
- **Day 1:** production Compose uses GitHub remote Git build context, Dockerfile stays in repo, SQLite named volume and port 5088 are configured; local Windows override is optional.
- **Day 3:** on a clean Linux host (no checked-out source), build from the pinned Git ref using only Compose and local configuration, verify migration, health, UI, updates and data persistence; record blockers instead of claiming success if unavailable.

## DEP-004 Public repository constraints (confirmed)

Day 1 must add `.gitignore`, `.dockerignore`, and safe `.env.example`, plus public GitHub pinned-ref remote-build configuration. Day 3 verify that no production database, secrets, real IP inventory, or user directory enters Git or the Docker image; test remote build without credentials and persistence.