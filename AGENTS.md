## Confirmed BR-020: local account provisioning
Only Super Admin provisions users and resets temporary passwords. No self-registration. First login with an admin-issued password MUST force a password change before normal application access, including JSON APIs. Do not hardcode or leak credentials; secure one-time administrator bootstrap is CLI-only. Test access checks and mandatory password change.

# Instructions for Codex / Coding Agents

## Source of truth
1. `SPEC.md` defines functionality, validations, permissions and acceptance criteria.
2. `PLAN.md` defines implementation order and PR gates.
3. `TASKS.md` tracks verified work. Never check a task before verifying it.
4. `docs/decisions.md` records user-approved policy choices; conflicts require clarification.

## Coding standards
- Python 3.12; FastAPI; synchronous SQLAlchemy 2.x; Alembic; Pydantic v2; Jinja2; Bootstrap 5.3.
- Keep routers lean; place claim/release/queue/reservation business rules in testable services.
- Keep HTML and API paths as separate interfaces to the same service methods.
- Never use `Base.metadata.create_all()` during normal app startup. Use Alembic migrations.
- No stub routes, fake data presented as production behavior, TODOs for required MVP features, or implicit policy choices.
- RBAC BR-008: Lab Admin manages both Taiwan labs and all SUTs, including Lab/SUT CRUD, queue clearing and recorded force-release. Do not generate lab-scoped assignments/table. Only Super Admin can manage users, roles and system config.
- UTC timestamps at rest; timezone-aware boundary comparisons; display and input times in Asia/Taipei for both Taiwan labs. No multi-timezone preference UI in MVP.
- BR-009: never hard-delete SUTs. DELETE archives (with blocker checks for active usage/queue/current or future reservations); provide audited admin restore; exclude archives from regular dashboard and prohibit use actions; preserve history.
- Preserve referential integrity and history. Do not enable unsafe cascade deletes.
- Run SQLite in single-worker MVP; explicitly serialize conflicting writes. Do not trust unsupported row locking semantics in SQLite.
- Validate all inputs, authorize every mutation server-side, escape template output, protect forms/API against CSRF, and hash passwords. Never log credentials or commit `.env`.
- Use deterministic fixtures and temporary SQLite databases in tests; include boundary and concurrency tests.
- No external hardware-control actions or future-feature integrations in MVP.

## Work procedure
1. Inspect repo and read source-of-truth documents.
2. Identify current phase and any blocking unconfirmed decisions. Ask rather than guess.
3. Summarize files and tests about to change.
4. Implement only the selected task/phase, with migrations/tests.
5. Run the relevant tests/build; report exact commands and results (or why execution was impossible).
6. Update docs and checked tasks only for passing work.
7. Provide PR summary, manual QA steps, limitations and open questions.

## Expected architecture
```
backend/
  app/
    core/          # config, database, security, RBAC, CSRF
    models/
    schemas/
    services/
    routers/api/   # /api/v1
    routers/web/   # HTML / Jinja2
    templates/
    static/
    scripts/       # bootstrap_admin, seed
    main.py
  alembic/
  tests/
  requirements.txt
  Dockerfile
compose.yaml
.env.example
README.md
```

## Definition of done per task
Implementation, migration (if needed), targeted automated test, manual reproduction steps, no privilege bypass, no regressions in the relevant test suite. Never mark incomplete work as done.

## Explicit product boundary
- MVP is a status, reservation, queue and in-app notification tool only. Do not implement SUT access lockdown, SSH/BMC controls, disconnection, power operations, or forced access enforcement.
- `current_usages` exclusivity ensures consistent app records, not guaranteed exclusive physical access.
- Implement BR-003 as reservation check-in (`waiting_for_release`), in-app alerts and manual handoff, not a forced ownership transfer.

- BR-004 is confirmed: release notifies FIFO head; do not auto-create current usage. Only user-initiated Claim records use. BR-005 is confirmed: expire an unclaimed notification after 15 minutes, record an audit event, send in-app notices, and notify the next eligible FIFO user. Respect protected reservations, transactional races, worker restart/idempotency, and no hardware access control.

- BR-007 (confirmed): allow the same authenticated user to hold multiple *different* SUTs concurrently. Enforce active-usage uniqueness per SUT only. Maintain independent usage, release, overdue, and history records.

- BR-010 (confirmed): Never auto-generate SUT names. Admin enters the name when registering a SUT. Enforce unique `(lab_id, normalized_name)` including archived rows; normalize trimmed case-insensitive names and translate DB uniqueness violations into actionable validation/409 errors. Same name across different Labs is permitted.

## Confirmed BR-011 constraint

Do not impose a maximum Claim usage duration or auto-release an overdue usage. Expected time is advisory; show reminders and record actual elapsed duration on release. **BR-012:** reservation lengths are independently capped at 24 hours elapsed; do not apply that cap to Claim expected duration. **BR-013:** allow reservation starts only in the future and within 30 × 24 hours of submission (inclusive). Check UTC instants at request time, show Taiwan local time; do not cap Claim estimates or incorrectly require reservation end within the 30-day horizon.

**BR-014:** Only owner or Lab Admin/Super Admin may edit/cancel future confirmed reservations. `PUT /reservations/{id}` edits start/end/purpose and rechecks BR-012, BR-013 from edit time, overlap and state inside one transaction; cancellation preserves records and triggers schedule/queue refresh. Never mutate an already-started or checked-in reservation; test ownership and conflict paths.

- BR-015 (confirmed): allow current holder (and admins) to update active usage expected end without Release/re-Claim; warn and require explicit acknowledgement when a reservation overlaps, but permit saving. Recheck and audit atomically. No auto-release or hardware access action.

- BR-016 (confirmed): never create a direct SUT user-to-user transfer/handover path in MVP. Release then separately authorized manual Claim; honor reservation/queue priority and audit both operations. No physical SUT handover/control.


## Confirmed BR-017 — Operational availability
Distinguish the administrative `normal` / `maintenance` / `out_of_service` flag from recorded usage and reservations. Never silently clear history, queue, reservation, or active usage when an admin marks a SUT unavailable. Prevent only *new application registrations*; never add physical lockout/device access control. All writes are admin-only, audited, and exercised by tests.


## BR-018 — Polling refresh rule (confirmed)
Dashboard, SUT Detail and in-app notifications use simple authenticated **read-only HTTP polling every 30 seconds**. No WebSocket, SSE or frontend framework in MVP. Reconcile returned status into the UI without losing input/filter state; show stale-state feedback on errors, avoid duplicate notices, and refresh immediately after successful user actions. Never perform state-changing work as a side effect of GET/polling. Background workers and POST/PATCH/DELETE services own expiration and transitions.


### BR-019 notification channel scope (confirmed)
MVP notifications MUST be stored in-app and may also display browser Notification API alerts after explicit user opt-in, while the page is open. No automatic permission request on load. Handle unsupported/denied permission, HTTPS secure-context constraints, and duplicate polling alerts gracefully. Read-only polling never marks notifications read. Do not add SMTP, Microsoft Teams integration, browser push, service workers or promise closed-browser delivery. Email/Teams are future-only.

### BR-021 account deactivation (confirmed)
Only Super Admin may deactivate/reactivate accounts. Deny disabled users' current sessions and all protected actions, show administrators their outstanding SUT usages, queue entries and future reservations, and require explicit authorized follow-up for cleanup. Never auto-release usage, remove queue records, cancel reservations, or control a physical SUT as part of deactivation. Ensure inactive queue members cannot block next eligible offers, retain audit/history, and block deactivating the last active Super Admin.


## BR-022 internal coordination data (confirmed)
Expose RD work email, display name, team, scheduling information and recorded purposes to authenticated team members on relevant coordination pages. Never expose private credentials, auth fields, or full user rows. Keep APIs/polling authenticated and verify safe response projections.

## BR-023: User profile permissions (confirmed)
Allow active users to change only their own display name, team, work email and password. Implement server-side field allowlisting; never trust client-supplied user IDs or allow user-driven role, username, status, or security-flag changes. Verify current password and rotate other sessions for password changes; protect browser forms with CSRF, enforce unique work emails, audit safe metadata and test unauthorized/mass-assignment attempts. BR-020 first-login password-change requirement takes precedence.


## BR-024: Usage History preservation (Confirmed)
Treat usage history as indefinite-retention operational records. Never implement a time-based history purge or cascade-delete history when a SUT is archived or user is deactivated. Preserve attribution and timestamps, test idempotent release-to-history, and document backups separately from retention policy.

## BR-025 dashboard display constraint
Implement one shared dashboard SUT query/status representation with two Bootstrap presentations: Card (default) and Table (user toggle). Keep search/filter and 30-second polling state consistent across layouts. Use lightweight vanilla JavaScript; avoid duplicating backend queries/business rules or introducing a SPA framework.


## BR-026 Dashboard reservation content rule
Do not render the same reservation summary in both layouts. Card = nearest upcoming valid reservation only; Table = all valid reservations overlapping the rolling next 24 hours per SUT. Use server time/UTC for window comparisons and Asia/Taipei for display. Retain BR-025 Card default, common filters and BR-018 polling. No new SPA framework.

## BR-027 Dashboard quick actions
Dashboard Card/Table modes must offer Claim, Join Queue and Reserve through accessible Bootstrap modals. Call existing authenticated application service/API paths; do not duplicate state transitions in JavaScript or make frontend visibility a permission boundary. Respect BR-011/012/013/015 and all queue/reservation policies. Keep current filters/view and unsaved modal input across BR-018 refreshes; update dashboard immediately after successful actions. No hardware access control.


## Three-day sprint execution
When asked to deliver in three days, read `SPRINT_3DAY.md`. Do not claim full MVP completion without executing validation gates. Prefer correct small PRs; state which confirmed requirements remain unimplemented. Never bypass authorization, record integrity, queue/reservation timing tests, or secure first-login handling to hit a calendar deadline. BR-028 Dashboard offers ONLY Name (default) and Status sort, shared across Card/Table.

## Full-MVP three-day mandate (confirmed Option A)
Complete BR-001 through BR-028; see `SPRINT_3DAY.md` and `CODEX_START_PROMPT.md`. Three days is a target, not permission to ship partial functionality. Do not claim completion until every acceptance condition and command is verified. Maintain `docs/implementation-status.md` as evidence.

## Deployment constraint — DEP-001
Deploy to a single internal Docker host via browser `http://<server-ip>:5088/` (example 10.88.26.99). Code and Compose must not embed the IP. Primary production operators use image-only compose.deploy.yaml plus host-managed secrets under DEP-007. Retain compose.yaml GitHub Remote Build as an optional developer/alternative path. Do not git clone during entrypoint. Publish 5088:80, persist SQLite outside image, support backups and one effective expiration scheduler. Do not claim LAN reachability was tested unless it actually was. Desktop notifications on LAN HTTP may be blocked; in-app notifications must remain usable. See SPEC.md DEP-001.



## DEP-002 production deployment mandate
DEP-007 supersedes the primary operator path with Docker Hub image-only Compose; GitHub Remote Build remains an optional developer path instead of copying/cloning repo onto Linux. Root Dockerfile lives in GitHub and is fetched during build; only Compose and host-managed configuration/secrets are stored on Linux. Pin a Git ref for production, never embed credentials, maintain named SQLite volume and health/migration startup. Explicitly test clean-host deployment and note manual rebuilds for GitHub updates. See SPEC.md DEP-002.

## Public repository safety (DEP-004)

The source repository is PUBLIC. Never commit secrets, environment files, real employee emails, real SUT BMC/Host IP inventories, production data, SQLite DBs, backups, or export files. Supply `.env.example` with placeholders and fictional seed data only. Use `.gitignore` and `.dockerignore`. Production uses a tested public Docker Hub version/digest without publisher credentials on the server; optional public GitHub Remote Build requires no GitHub token. Do not enable unauthenticated access to SUT inventory or user contact information.

## DEP-007 — Docker Hub image deployment supersedes the primary Remote Build path
Confirmed by Issue #6: release tested Linux amd64 images to `mirage315/sut-reservation-management` on explicit `v*` version tags only. Use scoped GitHub Actions secrets `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`, full-SHA pinned actions and successful automated checks before publishing; record version/source/digest provenance and verify an anonymous published-digest pull. Production administrators use image-only `compose.deploy.yaml` with a version/digest (never default latest), a securely supplied persistent SECRET_KEY, no source checkout/build. Keep 5088:80, non-root UID 10001, all capabilities dropped, no-new-privileges, private-network port-80 sysctl, Alembic startup and named SQLite volume. GitHub Remote Build remains optional for developers. Preserve the existing project/volume when switching deployment files; back up before schema upgrades and do not assume an old image supports a newer database. Do not claim registry publication, a separate-server deployment or LAN acceptance without actual evidence. See docs/deployment.md and docs/dep007-verification.md.


## DEP-008 — Administrator deployment / bind storage (confirmed)
The project owner's DEP-008 request supersedes Named Volume requirements **only for the primary image-only production deployment**. `compose.deploy.yaml` uses long-form bind `/data/sut-reservation-data` → `/app/data`, with `create_host_path: false`; operators verify the persistent `/data` mount and prepare UID/GID 10001 ownership/mode 700. Existing Named Volumes must not be deleted or migrated automatically. The optional Remote Build path and disposable recovery test volumes remain Named Volumes. Preserve the published v1.0.0 image, application code, 5088:80, non-root/security/deadline/migration behavior. See docs/deployment.md for reviewed Compose selection, secure local configuration, cold backup/empty-directory restore, upgrade and manual migration. Actual production/LAN validation remains external.
