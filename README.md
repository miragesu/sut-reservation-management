## BR-020 MVP local account policy
Super Admin provisions all RD accounts and delivers initial temporary passwords via a secure out-of-band process. Users must change their password on first login. Self-registration, email invites, and Teams onboarding are not included. The initial Super Admin is bootstrapped with a one-time CLI command implemented in Phase 1; never use a hardcoded default password.

# SUT Reservation & Queue Management System

GitHub-ready **planning pack** for the MVP. This package contains specifications and Codex execution instructions; it does **not** yet contain application code.

## Read order
1. `SPEC.md`: product rules and acceptance criteria.
2. `PLAN.md`: implementation phases.
3. `TASKS.md`: tracked checklist.
4. `AGENTS.md`: coding agent guidance.

## Important
`SPEC.md` section 11 tracks confirmed decisions and remaining open questions. BR-008 RBAC is confirmed; resolve remaining deletion/naming and scheduling-limit decisions before coding those features.

## Suggested workflow
1. Create an empty repository and commit these documents.
2. Resolve remaining open decisions and record them in `docs/decisions.md`.
3. Ask Codex to execute the Initial Codex Task Prompt in `PLAN.md`.
4. Review/test and merge PRs phase-by-phase.
5. Do not treat AI-generated code as production-ready until the acceptance tests and security review pass.

### Scope boundary
MVP records scheduling and self-reported use, displays conflicts and in-app reminders; it does not control or block access to SUT hardware. See `docs/decisions.md` for BR-001 through BR-003.

> MVP boundary: app records and reminders are advisory; no device access restriction, forced disconnection, or remote power control. BR-001/002/003/004/005 are confirmed; BR-005 uses a 15-minute manual Claim deadline and audited FIFO handoff.

## MVP deployment scope (BR-006)

Two labs in Taiwan, approximately 20 SUTs total. One application instance and persistent SQLite. All displayed/input scheduling times use `Asia/Taipei`; timestamps are stored as UTC. US labs and per-user timezone selection are out of scope.

### Confirmed admin policy BR-008
Every Lab Admin manages both Taiwan labs and all SUTs, including Lab/SUT CRUD, queue clearing and recorded force-release; only Super Admin manages users, roles and system configuration. No lab-assignment mapping.

### Confirmed usage rule BR-007
One RD may coordinate and Claim several different SUTs simultaneously. Each SUT maintains separate usage/Release/history records; this app does not restrict access to the physical devices.

### Confirmed SUT lifecycle BR-009
SUT “Delete” archives the item (no hard delete); history remains. Admins can restore an archived SUT. Archiving is blocked if active usage, queue or ongoing/future reservations remain. Archived SUTs are excluded from the normal dashboard and new coordination actions.

### BR-010 — SUT naming
Lab Admin/Super Admin names each device when creating its record. Names must be unique within the Lab (including archived records), while separate Labs may reuse names; whitespace/case variants count as duplicates.

### BR-011 confirmed

Users can enter multi-day expected Claim durations without a business maximum. Overdue SUT usage remains recorded as In Use with an Overdue reminder until manually released. Reservation limits are a separate pending decision.

### Confirmed BR-012 — Reservation duration
Each reservation must be longer than zero and no longer than **24 hours**. A Claim usage estimate remains uncapped under BR-011. **BR-013:** a reservation can start in the next 30 days (inclusive, 30 × 24 hours from submission), but not in the past. Its duration remains capped at 24 hours. Display uses Taiwan time; server comparison uses UTC.

**BR-014:** A user can edit or cancel their own upcoming confirmed reservation, and any Lab Admin/Super Admin can manage those of either lab. Editing reruns 24-hour duration, 30-day advance window, and overlap checks; historical reservations remain intact.

**BR-015 confirmed:** Active SUT holder may extend the estimated end time directly; reservation overlap triggers an explicit warning and acknowledgement, not a block or physical device action.

**BR-016 confirmed:** No direct transfer between RD users. Current holder Releases; the next eligible user manually Claims after reservation/queue priority rules, with separate history records.


**BR-017 confirmed:** Admins can mark a SUT as `Maintenance` or `Out of Service` with a reason. The dashboard shows the operational condition and keeps existing activity visible. New registrations are paused while the SUT is unavailable; no physical device access is blocked or disconnected.


**BR-018 confirmed:** While open, Dashboard, SUT Detail and in-app notification area fetch updated statuses every 30 seconds via HTTP polling (no WebSocket/SSE). Read-only polling must not change usage or queue state; network errors display stale-data feedback.


**BR-019 notification decision:** MVP uses persistent in-app notices plus optional browser desktop notifications activated by the user. The website must remain open for desktop alerts; permission and a suitable browser/secure context (HTTPS or localhost) are required. Email and Microsoft Teams notifications are deferred to a later version.

**BR-021 confirmed:** Super Admin may disable accounts, immediately preventing further authenticated access. The application lists all outstanding SUT claims, Queue entries and future Reservations for admin follow-up; it does **not** automatically Release, remove queue records or cancel reservations. Recorded history is preserved, and admins manually resolve outstanding entries using permitted actions.


## BR-022 colleague coordination visibility (confirmed)
For internal coordination, signed-in RD users can see the active user, queued/reserved colleagues, their team, work email, and recorded purpose/time on SUT pages. Contact details are not public and do not appear in anonymous API responses.

**BR-023 account profile:** Once the mandatory first-login password change is complete, RD users can edit their own display name, team and work email via `/profile`, and change their password with current-password verification. Account name, roles, activation and privileges remain Super Admin-managed. Profile changes are shown in SUT coordination views.


### Confirmed BR-024: Usage History retention
The application retains usage histories indefinitely; MVP has no auto-purge or retention timeout. Archiving a SUT or disabling a user does not erase histories. This application-level policy does not replace SQLite backup/disaster-recovery procedures.

## Confirmed dashboard UX (BR-025)
The MVP Dashboard defaults to Lab-grouped SUT cards and provides a Card/Table layout toggle. Both views share filters/search and the same status data; the visible layout refreshes every 30 seconds without losing the user's selection.


## Confirmed Dashboard reservation summaries (BR-026)
Card view (default) presents only the next upcoming reservation per SUT. Table view shows all valid bookings overlapping the next rolling 24 hours per SUT. Both views share filters and refresh every 30 seconds, with timestamps displayed in Taiwan time.

## Dashboard quick actions (BR-027 confirmed)
Both Card and Table modes include Bootstrap modal actions for Claim, Join Queue and Reserve, in addition to links to SUT Detail. Modals use the same permissions/validations as the normal SUT flows and retain the current Dashboard view and filters. Submissions refresh the display immediately; periodic 30-second status polling does not clear an open form. These actions update only the coordination system, not the physical SUT.


## Dashboard sorting (BR-028)
Both Card and Table modes support user-selected **Name** (default) and **Status** sorting inside each Lab; the selection persists through view/filters/refresh. No other Dashboard sort options are required for MVP.

## Three-day Codex sprint
See [`SPRINT_3DAY.md`](SPRINT_3DAY.md) for daily milestones, acceptance gates, and explicit deferrals. Three days is a target for a verifiable working increment, not a guarantee that every v1.0 feature is production-ready.

## Codex full-MVP kickoff (confirmed three-day target)
See [CODEX_START_PROMPT.md](CODEX_START_PROMPT.md) for the agent prompt, [SPRINT_3DAY.md](SPRINT_3DAY.md) for the critical path, and [docs/implementation-status.md](docs/implementation-status.md) for actual delivery evidence. Target is all BR-001–BR-028, not a beta subset. Three days is aspirational; quality gates are mandatory. This repo pack is documentation, not the implemented app.

## DEP-001 — Deploy to internal lab server
Expected example URL: `http://10.88.26.99:5088/` (replace with your server's actual address). Use the approved GitHub Remote Build approach: only `compose.yaml` and a locally created `.env` need to be placed on the Linux server; Docker obtains the GitHub source (including Dockerfile) at build time. Do not clone source during container startup. Codex must create a functioning `compose.yaml` publishing `5088:8000`, durable `./data` SQLite storage, migration-before-startup and secure credentials in `.env`. Following implementation, start with `docker compose up -d --build`, inspect `docker compose logs -f`, and verify `curl http://localhost:5088/health` on the server. Make sure host/network firewalls allow trusted LAN clients on TCP 5088. Never run `docker compose down -v` as routine maintenance. Back up persisted SQLite carefully before upgrades. In-app alerts work on HTTP; opt-in browser desktop notifications may require HTTPS and a trusted certificate. Actual 10.88.26.99 access cannot be verified from this planning document.



## DEP-002 — Selected production path: Compose + GitHub Remote Build
Only place `compose.yaml` and a locally configured `.env` (if required) on the Linux server. During `docker compose up -d --build`, the Docker builder obtains source and `Dockerfile` from the GitHub remote context. The application must ship an example production Compose file at repo root with a pinned ref; see SPEC.md DEP-002. Docker/Git build support, outbound GitHub access and private-repo authentication (if applicable) are prerequisites. Do not clone the repo at container startup. SQLite persists in a named volume, independently of image and container lifecycle.

## Repository visibility: Public (DEP-004)

This is a **public code repository**, not a public service. Deploy behind the trusted corporate LAN and require authentication. Never commit production SQLite files, actual BMC/Host IP inventory, user email lists, or credentials. Production application data is in a Docker named volume. GitHub remote build for a public repo requires no private repo token, but the host still needs outbound access to GitHub and a supported Git/BuildKit setup. Use a pinned release/commit instead of `main` for repeatable production deployment.