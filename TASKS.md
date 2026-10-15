# Implementation Checklist

> Check boxes only after successful verification. Link PR or test evidence in the PR description.
> Day 1/2/3 evidence: `docs/implementation-status.md`, `docs/day2-verification.md` and `docs/day3-verification.md`. Checked deployment items refer to local Compose and source-free pinned GitHub Remote Build on the cloud daemon, not the actual LAN host or a newly provisioned production OS. External/owner gates remain unchecked; local automated/browser/deployment evidence is distinguished in the status document.

## Phase 0 — Decision gate
- [x] Confirm BR-008: Lab Admin manages both labs, creates/deletes labs and SUTs, force-releases records and clears queues; user management remains Super Admin only
- [x] Confirm FIFO queue temporary-use rule before an upcoming reservation
- [x] Confirm manual reservation claim and 15-minute no-show expiration
- [x] Confirm BR-003: checked-in reservation holder waits for recorded release; manual Claim; no forced access restrictions
- [x] Confirm BR-004: FIFO head notified upon release, manual Claim required
- [x] Confirm BR-005: 15-minute notified-user Claim deadline; expire/audit and notify next eligible user
- [x] Confirm BR-006: Taiwan-only deployment, two labs/~20 SUTs, UI in Asia/Taipei; UTC at rest
- [x] Confirm BR-009: SUT delete = archive, historical data retained, default inventory excludes archives, admin restore; block archive while actively used, queued or reserved
- [x] Confirm BR-010: Admin manually names SUT; names unique within each Lab (including archives) but reusable across different Labs
- [x] Confirm BR-011: no maximum on Claim expected duration; overdue shows reminder only, no auto-release
- [x] BR-012: reservation duration is >0 and <=24 hours (elapsed duration), independently of BR-011 Claim estimates
- [x] BR-013: reservation start must be future and no more than 30 × 24 hours ahead (inclusive), validated using UTC instants; reservation length independently capped at 24 hours
- [x] Confirm BR-007: one user may Claim multiple distinct SUTs concurrently; each has independent usage and history
- [x] Record confirmed BR-001/002/003 in `SPEC.md` and `docs/decisions.md` (other Phase 0 decisions remain open)

- [x] Confirm BR-020: Super Admin creates local accounts, issues temporary password, and first login requires password change; no public registration
- [x] BR-020 tests: CLI bootstrap, temporary password hashed, forced password change for web/API, create/reset role enforcement and audit hygiene

## Phase 1 — Foundation
- [x] App factory/main, settings and `/health`
- [x] SQLAlchemy 2.x models/relationships/constraints
- [x] Alembic initial migration
- [x] Local auth (password hash, login/logout, secure session, CSRF)
- [x] Role-based authorization dependencies (no lab assignment mapping)
- [x] Shared Bootstrap template and error pages
- [x] Admin bootstrap CLI and dev seed script
- [x] Dockerfile, compose, persistent SQLite data volume
- [x] `.env.example`, `.gitignore`, README
- [x] Pytest fixtures and local test/smoke runners (see Day 1 evidence)
- [x] Hosted GitHub Actions execution verified at final application `eb17c6f` — run 38736460114 succeeds.

## Phase 2 — Inventory
- [x] Lab HTML and JSON CRUD with role-based all-lab access (BR-008)
- [x] SUT HTML and JSON CRUD: archive-only DELETE, blocked-conflict 409, admin restore, include_archived admin filter, historical linkage preserved (BR-009)
- [x] Test archive/restore role permissions, archive conflicts, history retention, exclusion from KPIs and inability to Claim/Queue/Reserve archived devices
- [x] Dashboard KPIs and Lab-grouped Card default plus Table toggle (BR-025)
- [x] SUT list search/filter/pagination
- [x] SUT detail basic information
- [x] Test BR-010: create same name in different Labs succeeds; case-insensitive/trim-equivalent duplicate in same Lab returns 409 / user-friendly form error; rename conflict rejected; archived names remain reserved; DB uniqueness handles concurrent submissions; FK protections and missing resource 404
- [x] Test Lab Admin editing/force-releasing/clearing queues in either lab; User denied; Super Admin user management only

## Phase 3 — Usage & queue
- [x] Claim with positive, overflow-safe expected duration; 1/2/4/8 hour presets and multi-day custom duration, no business cap (BR-011)
- [x] Exclusive current usage **per SUT** and serialized writes; never impose per-user one-SUT restriction (BR-007)
- [x] Own release and admin force release
- [x] Exactly-once usage history
- [x] Queue join/leave with duplicate prevention
- [x] Queue FIFO position computation, clear by admin
- [x] Atomic queue-head notification on release without creating current usage
- [x] Only notified FIFO head can manually Claim; Claim clears offer and records usage
- [x] Test that a notified user is not displayed as In Use before Claim
- [x] BR-005 offer expires at notified_at + 15 minutes without Claim; audit timeout and notify affected user
- [x] Advance to next eligible FIFO head with new 15-minute offer; preserve protected reservation priority
- [x] Expired user may rejoin at tail; concurrent Claim/expiry, repeated sweep and restart are safe
- [x] History listing/filter; BR-011 overdue shown on dashboard/detail/My Usage with in-app reminders, while usage stays active
- [x] BR-011 tests: multi-day claim allowed, zero/negative/invalid duration rejected, no auto-release at deadline, history computes actual elapsed time
- [x] Concurrent claim and queue race tests
- [x] BR-007 tests: same user Claims two distinct SUTs, independently Releases one, other remains active, histories separate; same SUT still rejects duplicate active claim

## Phase 4 — Reservations
- [x] Create/list/cancel reservation in API and HTML
- [x] BR-013 API and HTML validation: accept future start exactly 30 days ahead, reject start beyond 30 days and starts in past; keep timezone conversions consistent
- [x] BR-012 server-side and form validation: accept exactly 24 hours, reject >24 hours/zero/negative/inverted endpoints with clear 422/API or form error; do not silently shorten
- [x] Validate half-open overlap and active usage conflict
- [x] Reservation-aware claim and queue promotion
- [x] Calendar page with timezone labels
- [x] Effective status calculation across all pages
- [x] Reservation boundary/Asia-Taipei display/race tests
- [x] Background no-show processing at 15 minutes (no page visit; retry-safe and restart-safe)
- [x] No-show releases reservation protection and tries FIFO head notification without double claim
- [x] Upcoming reservation prominently warned; no enforced hardware cutoff or forced handover
- [x] BR-003 check-in while occupied -> waiting_for_release, not no_show
- [x] Release prioritizes checked-in reservation by notifying holder to Claim (no auto-claim)
- [x] In-app warning to current user when reserved holder checks in

## Phase 5 — Release validation
- [x] `docker compose up --build` starts cleanly
- [x] Fresh DB `alembic upgrade head` works
- [x] Restart/recreate container preserves SQLite DB
- [x] `pytest` passes, CI green for final application SHA `eb17c6f` (103 cases; hosted run 38736460114).
- [x] End-to-end manual smoke walkthrough documented
- [x] README and API docs match actual behavior
- [x] No TODOs for MVP requirements, no exposed credentials
- [ ] Final acceptance checklist signed off by project owner

- [x] Confirm BR-014 business policy (implementation tracked below): owner can edit/cancel own upcoming confirmed reservation; admins can edit/cancel any; validate edited booking and audit changes

- [x] BR-014 Phase 4: reservation update and cancellation APIs/UI; owner/admin authorization, validation against BR-012/013, overlap, state guard, audit, queue refresh, boundary/race tests

- [x] BR-015 business policy confirmed: edit expected end without re-Claim; advisory reservation conflict with explicit confirmation
- [x] Phase 3 BR-015: owner/admin edit active expected end (API + HTML), same usage record, no upper duration cap, validation and audit
- [x] Phase 3 BR-015: reservation conflict warning requires affirmative acknowledgement, no denial after acknowledgement and no reservation mutation
- [x] Phase 3 BR-015 tests: normal extension, overlap/acknowledgement, permission, missing usage, stale/concurrent updates, history unchanged

- [x] BR-016 confirmed: no direct handover; Release followed by separately authorized manual Claim.
- [x] Phase 3 BR-016: no handover API/UI or current user reassignment.
- [x] Phase 3 BR-016 tests: Release makes distinct history, queue/reservation priority remains, next user manually Claims, no automatic new usage or bypass.


## BR-017 — Maintenance / Out of Service acceptance checks (confirmed)
- [x] Migration adds operational state, reason, update timestamp and actor to SUT; default `normal`.
- [x] Only Lab Admin/Super Admin may change the state; non-normal states require an explanatory reason and changes are audited.
- [x] Dashboard, detail, list, calendar and relevant filters show `Maintenance` / `Out of Service` and reason, with active use conflicts still visible.
- [x] New Claim, Queue join and Reservation creation fail with an actionable `409` for non-normal SUTs (also when racing with a state change).
- [x] Existing usage/history/queue/reservations are not silently deleted or released; Release/leave Queue remain possible.
- [x] Queue offers are paused safely while unavailable and re-evaluated upon return to normal, respecting reservation priority and avoiding duplicate notices.
- [x] Pytest covers permissions, invalid missing reason, state changes and restoration, ongoing usage and existing reservations, and no hardware calls.


## BR-018 — Status / notification 30-second refresh (confirmed)
- [x] Confirm BR-018: Option B — HTTP polling every 30 seconds on Dashboard, SUT Detail and notification area; no WebSocket/SSE in MVP.
- [x] Authenticated read-only status and notification endpoints return current state without side effects.
- [x] Dashboard, SUT Detail and in-app notification UI update automatically every 30 seconds, preserving in-progress form entries and filters.
- [x] Successful actions trigger immediate relevant status refresh; polling handles changes by other users.
- [x] Network/API failure keeps prior values, shows stale/retry cue and retries; no duplicate notification display.
- [x] Tests verify response authorization, 30-second client interval, external changes becoming visible, and no state mutation by polling.


## BR-019 — In-app + optional browser desktop notifications (confirmed)
- [x] Confirm BR-019 Option B: in-app + opt-in browser desktop notifications; Email/Teams deferred.
- [x] Create persisted, user-scoped notification records with event identifiers and `read_at`; deliver at most once per logical event/recipient despite retries.
- [x] Implement notification bell, unread count, notification list and explicit mark-read action.
- [x] Fetch new/unread notifications using existing 30-second read-only HTTP polling (BR-018).
- [x] Provide user-click permission opt-in; gracefully handle denied/unsupported/insecure contexts.
- [x] Show best-effort desktop alerts while site is open and avoid duplicate notifications across polls.
- [x] Cover permissions, recipient access, read semantics, dedupe, no GET side effects and failure fallback in tests.
- [x] Document limits (HTTPS/localhost; browser/OS permission; no notifications guaranteed when website is closed).
- [x] Do not implement Email, Teams, service-worker push or SMTP in MVP.

## BR-021 — Account deactivation with admin resource review (confirmed)
- [x] Confirm Option B: disable login and show affected resources; do not auto Release/leave Queue/cancel Reservations.
- [x] Super Admin-only disable/reactivate API + UI, audit actor/time/reason, and last active Super Admin protection.
- [x] Disable invalidates/rejects all existing sessions and mutations for affected user; historical references intact.
- [x] Impact preview and Admin `Needs attention` list active usages, queue entries and upcoming reservations with SUT/Lab context.
- [x] Verify disabling user leaves existing usage/queue/reservation data untouched, while authorized admins can take explicit audited actions.
- [x] Queue notification skips inactive users without silently deleting history or blocking subsequent eligible people.
- [x] Tests for role authorization, session rejection, no auto cleanup, reactivation, retention and race/expiry paths.


## BR-022 — Colleague information visibility (confirmed)
- [x] Confirm Option C: logged-in users can see other RD display names, teams, work emails, purposes (where recorded), and scheduling times.
- [x] Add `users.team` and optional `current_usages.purpose`, with Alembic upgrade/backfill strategy.
- [x] Show name, team, email (`mailto:`), time, purpose on SUT detail/queue/reservation views where relevant.
- [x] Authenticated API/polling includes only required coordination fields; no anonymous access, password hashes or session/security fields.
- [x] Tests cover permission boundaries, visibility, missing purpose, disabled-account history, and no email in desktop notification payloads.

## BR-023 — User profile self-service (Confirmed)
- [x] Confirm Option B: RD can edit own display name, team, work email and password; no self-service username/role/permission change.
- [x] Build `/profile` edit form and authenticated `GET/PATCH /api/v1/users/me`; allowlist editable fields on server.
- [x] Reuse secure password-change endpoint, require current password and invalidate other sessions where applicable.
- [x] Validate required fields, work-email format and unique normalized email; show clear UI/API errors.
- [x] Enforce first-login password-change gate and reject attempts to edit others or mass-assign username/role/status.
- [x] Audit safe field changes and verify SUT/Queue/Reservation contact info reflects updated profile without mutating historical user IDs.
- [x] Tests for successful updates, invalid/duplicate email, forbidden fields, authentication, CSRF, and password changes.


## BR-024 — Usage History retention (Confirmed: Option A)
- [x] Confirm indefinite application-level retention; no automatic deletion.
- [x] Ensure Release/Force Release creates one history row with actual start/end/duration; retry does not duplicate it.
- [x] Ensure SUT archive/restore, user deactivation and profile changes preserve histories and user/SUT attribution.
- [x] Check database foreign keys/ORM cascade policies cannot delete history by accident.
- [x] Confirm `/history` and APIs offer user/SUT/date filtering, pagination, and read-only queries.
- [x] Verify no TTL, history purge scheduler, deletion endpoint, or automatic retention job exists in MVP.
- [x] Add tests for retrieval after archival/deactivation, history list filters and persistence across app restarts; document backup recommendations.

## BR-025 — Dashboard layout switch acceptance (Confirmed: C)
- [x] Confirm Card default + optional Table view; no separate datasets.
- [x] Default Dashboard groups cards by Lab with status, current user and next reservation context.
- [x] Accessible Card/Table toggle renders table columns for Lab/name/platform/status/current holder/expected end.
- [x] Search and filters are shared, and switching views preserves criteria and visible results.
- [x] BR-018 30-second polling updates cards/table and KPI from a single status source, without resetting the toggle or filters; stale-state warning on failure.
- [x] Automated tests cover both layouts, filter parity, archived exclusions, maintenance flags and polling refresh.


## BR-026 — Dashboard reservation visibility (Confirmed: custom)
- [x] Confirm Card = next upcoming reservation only; Table = all valid reservations in the rolling next 24h.
- [x] Implement server-side next-booking projection and per-SUT rolling-24h reservation lists, filtered to valid states.
- [x] Card shows at most one booking (name + TW start/end) or empty message.
- [x] Table shows every booking overlapping `[now, now+24h)` in chronological order, with clear multi-booking layout.
- [x] Include window-boundary overlapping bookings, omit expired/cancelled/no-show; respect timezone and status rules.
- [x] Preserve BR-025 shared SUT filters/view switch and BR-018 polling without interrupting input.
- [x] Test booking counts 0/1/multiple, boundaries, clock advancement, state updates, view switch, and polling.

## BR-027 — Dashboard quick actions (Confirmed: B)
- [x] Confirm Dashboard supports Claim, Join Queue and Reserve using Bootstrap modals in both Card and Table views.
- [x] Build reusable modal components prefilled with the selected SUT and accessible labels/focus management.
- [x] Claim modal: duration/custom time, optional purpose, upcoming reservation warning and confirmation where applicable; use shared Claim API/service.
- [x] Queue modal: display position/eligibility, prevent duplicate registration; use existing Queue service.
- [x] Reserve modal: start/end/purpose with Asia/Taipei formatting and BR-012/013 validation/conflict handling.
- [x] Enforce role/device/queue/reservation rules server-side and handle races/duplicate submissions.
- [x] Success closes modal and immediately refreshes affected SUT, stats and notices without losing search, filters, active view, or scroll.
- [x] Errors preserve modal inputs and explain corrective action; 30-second polling never resets an open modal or unsaved input.
- [x] Test both views, accessible modal interaction, validation, API authorization, success/failure, race cases and polling safety.


## BR-028 — Dashboard sorting (Confirmed: customized C)
- [x] Confirm only `Name` and `Status` options; default is Name.
- [x] Name uses case-insensitive natural ascending order within Lab; tie-break by SUT ID.
- [x] Status uses Available → Reserved → In Use → Maintenance → Out of Service, then name/ID, within Lab.
- [x] Card/Table, filtering and 30s polling retain the selected sort choice.
- [x] Cover Name/Status, cross-Lab groups, archived filtering, overdue indicator and stable ties with tests.

## Three-day sprint checkpoint
- [ ] Follow `SPRINT_3DAY.md`; capture actual command outputs and evidence for each day gate.
- [ ] Clearly label unimplemented/deferred MVP features in final handoff; NEVER check a task as complete without successful verification.
- [ ] Run fresh DB migration, test suite, Docker smoke path, and security/role checks before claiming ready for internal deployment.

## Full-MVP execution gate (confirmed Option A)
- [ ] Every confirmed BR-001 to BR-028 has passing behavior tests and documented manual checks; no silent postponement.
- [ ] Day 1, Day 2, Day 3 gates from `SPRINT_3DAY.md` each have recorded commands/outcomes.
- [x] Concurrency and time-based reservation/queue expiry tests pass, including restart/idempotency.
- [x] Auth/RBAC, CSRF, DB migration, Docker persistence, Profile, notifications and dashboard checks pass for application SHA `eb17c6f`; actual LAN/owner gates remain separate.
- [x] `docs/implementation-status.md` shows PASS only with evidence.
- [ ] If Day 3 is incomplete, retain NOT DONE and continue; do not recast full MVP as beta.

## DEP-001 — LAN deployment acceptance (all required)
- [x] Supply deployable Dockerfile + compose.yaml and complete repository/image prerequisites.
- [x] DEP-006: map host TCP 5088 to container 80; verify non-root listener, health and port-binding isolation.
- [x] Serve login/root page and 200 `/health`; FastAPI binds 0.0.0.0 in container.
- [x] Fresh Alembic migration succeeds and fails startup visibly on error.
- [x] SQLite data persists across container restart and image rebuild, never stored only in writable container layer.
- [x] Bootstrap and secrets configured via env securely; no default hard-coded credentials.
- [x] 15-minute queue/no-show deadlines run without browser open and do not duplicate on restart.
- [x] Provide deploy/update/log/backup/restore instructions and LAN/firewall prerequisites.
- [ ] Verify browser can reach `http://<server-ip>:5088/` on actual internal host; if host not accessible, mark unverified, not passed.
- [ ] In-app notifications work over LAN HTTP; desktop notifications degrade gracefully when browser requires secure context.


## DEP-002 — GitHub Remote Build acceptance
- [x] Production `compose.yaml` obtains source + Dockerfile from pinned GitHub Git context, with no source checkout on server.
- [x] Container start does not clone/pull Git, and runtime contains no embedded Git credentials.
- [ ] Clean Linux host deploy with only Compose + local configuration succeeds via `docker compose up -d --build`.
- [x] Published `:5088`, `/health`, login, migrations and browser UI verified.
- [x] Named volume keeps SQLite data through rebuild and recreate; backup and rollback are documented.
- [x] Public vs private repo network/authentication requirements documented and tested as applicable.
- [x] Windows Docker local development override documented; production remains Linux remote-context build.
- [x] Explicit redeploy required after GitHub changes; release revision pinned for repeatability.

## DEP-004 — Public repository acceptance checklist

- [x] Compose performs GitHub remote build using a pinned public tag/commit and requires no token.
- [x] `.gitignore`, `.dockerignore`, `.env.example` exist and production `.env` is not committed.
- [ ] Git history and tracked files contain no actual secrets, RD contacts, production BMC/Host IP addresses, DB files, exports, or backups.
- [x] Example seed data is fictional and safe for public distribution.
- [x] SQLite persists in a Docker named volume, survives container rebuild, and is never committed.
- [ ] Port 5088 is available to trusted LAN users only, with login enforcement; public repository visibility does not imply a public service.

## Issue #2 — Day 2 acceptance checkpoint
- [x] Start from merged Day 1 `main` (`489b18f`); use `feat/day2-coordination`.
- [x] Read Issue #2 and confirmed specifications; record user-confirmed Queue admission rule.
- [x] Atomic Claim/Release/force-release, stable retry identities, complete durable Usage History.
- [x] FIFO/manual Claim, exact 15-minute expiry, checked-in reservation priority, inactive and maintenance eligibility.
- [x] Reservation create/view/edit/cancel, 24-hour/30-day boundaries, no-show/check-in and Calendar.
- [x] Background startup catch-up, periodic processing without HTTP/browser, interruption rollback and overlapping-worker deduplication.
- [x] Local lint/format/compile, 98 pytest cases, baseline and Day 2 Chromium flows, Docker migration/persistence/deadline smoke pass (details in evidence).
- [x] Day 2 implementation branch pushed; public pinned-ref Remote Build and source-free Compose deadline/persistence smoke pass at `344d305`.
- [x] Day 2 merged to main via PR #3 (confirmed by project owner); the original Day 2 agent API creation blocker is retained as historical evidence.

Day 2 code acceptance does not complete Day 3 or full MVP. Hosted CI and actual LAN/production-host checks remain unverified.

Historical Day 2 note: Detail/Inbox polling supplied the shared read-only controller. Day 3 verification now covers the notification/modal refresh and failure/deduplication behavior checked above.

## Issue #4 — Day 3 acceptance checkpoint
- [x] Start from merged Day 1/2 main `719c32e`; branch `feat/day3-ui-acceptance`.
- [x] Dashboard actions in Card/Table, shared state refresh, CSRF/conflict handling and retained modal input.
- [x] Complete recipient notification history/unread counts, desktop opt-in/fallback/deduplication, authenticated contact visibility.
- [x] Responsive navigation/calendar/history/detail, keyboard modal dismissal and fictional 2-lab/20-SUT browser fixtures.
- [x] BR-001–BR-028 implementation/test map recorded in `docs/day3-verification.md`.
- [x] Disposable local cold backup restored into a separate empty named volume, retaining sessions/history/notices and passing schema/integrity checks.
- [x] Published final Day 3 SHA `eb17c6f` Remote Build and source-free Compose/deadline/backup-restore checks pass; implementation branch pushed.
- [ ] Day 3 PR created — actual GitHub GraphQL creation returned Forbidden; pushed branch and reviewable PR body available for ChatGPT.
- [x] Hosted Actions result verified at final DEP-006 application SHA `eb17c6f` (run 38736460114).
- [ ] Actual production LAN host/firewall/two-client/backup rehearsal and project-owner acceptance.

Day 3 application evidence is distinct from full MVP production acceptance. Full MVP remains NOT DONE until external gates pass.

## DEP-006 — Updated deployment gate
- [x] Dockerfile EXPOSE/healthcheck, entrypoint and Compose consistently use container port 80.
- [x] UID 10001, all capabilities dropped, no-new-privileges; container-local binding permission verified without host changes.
- [x] Host 5088 → container 80 health, login and actual Chromium workflow pass.
- [x] Local build/Compose and published-SHA GitHub Remote Build pass; named-volume persistence and backup/restore retained.
- [ ] Production LAN host/firewall/two-client acceptance (requires company access).
