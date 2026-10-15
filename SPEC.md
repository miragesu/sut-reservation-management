# SUT Reservation & Queue Management System — Product Specification

Version: 1.5-draft | Scope: MVP | Source: user-provided v1.0 requirements

> **Status: review required before implementation.** Items tagged `DECISION` below are proposed defaults, not confirmed business requirements. Do not silently reinterpret them.

## 1. Purpose and scope
Internal web application to coordinate SUT (System Under Test) resources across two laboratories in Taiwan (approximately 20 SUTs total). Users: BMC, BIOS, Validation, FW and System teams. Goals: visible availability, self-reported claim/release, FIFO queues, advance reservations, searchable inventory, and auditable usage history.

### In scope
- Local username/password login and role-based authorization.
- Dashboard and search/filter by lab, platform, SUT name, owner team, and effective status.
- Lab and SUT CRUD by authorized administrators.
- SUT detail with current owner, expected end, queue, upcoming reservations, and actions.
- Exclusive claim/release, FIFO waitlist, queue auto-promotion on release.
- Reservation create/list/edit/cancel and a simple calendar view.
- Usage history with user/SUT/date filters.
- Admin user management needed to issue accounts and grant roles.
- Alembic migrations, persistent SQLite in Docker, automated tests, README and seeded development fixtures.

### Out of scope
Entra ID, Teams notifications, US labs/multi-timezone UI, OpenBMC/Redfish/IPMI power actions, auto-release upon expiry, PostgreSQL deployment, multi-node horizontally scaled deployment. Never automatically power on/off any hardware in MVP.

## 2. Technology and design constraints
- Python 3.12; FastAPI; synchronous SQLAlchemy 2.x sessions; Alembic; Pydantic v2 and pydantic-settings.
- SQLite for MVP, with foreign keys ON, a busy timeout, and one application process for concurrency safety. Plan schema to be portable to PostgreSQL later.
- HTML/Jinja2 server-rendered pages; Bootstrap 5.3; minimal vanilla JavaScript; no SPA.
- Auth via signed HttpOnly SameSite=Lax session cookie, with CSRF protection for browser mutations; password hashes using a maintained password hashing library (Argon2id preferred). No raw passwords, no hardcoded admin credentials.
- Store timestamps as timezone-aware UTC logically; serialize as ISO 8601 UTC. Render all UI date/times in `Asia/Taipei` (UTC+08:00). MVP does not require user timezone preferences or US-local display. Never use naive local timestamps for reservation comparisons.
- Separate models, schemas, services, API routers and HTML routers. Business rules belong in services reused by both API and pages.
- REST API under `/api/v1`; HTML routes separately; `/health` for liveness.

## 3. Roles and authorization
| Capability | User | Lab Admin | Super Admin |
|---|---|---|---|
| View lab/SUT/search/calendar/history | Yes | Yes | Yes |
| Claim/release own SUT | Yes | Yes | Yes |
| Join/leave own queue | Yes | Yes | Yes |
| Create/cancel own reservation | Yes | Yes | Yes |
| Create/edit/delete lab or SUT | No | All labs | All labs |
| Force release / clear queue | No | All labs | All labs |
| Manage users, roles, assignments/config | No | No | Yes |

**CONFIRMED BR-008:** Every Lab Admin can create, update, and delete labs and SUTs across both Taiwan labs, subject to normal deletion safeguards. Every Lab Admin can force-release recorded usage and clear queues across both labs. No lab-scoped assignments are needed in MVP. Only Super Admin manages users, roles and system configuration.

- No anonymous read/write access except `/login`, `/health`, and static assets.
- API authorization is server-side, regardless of whether UI buttons are hidden.
- **CONFIRMED BR-020 — Super Admin provisions user accounts:** No public sign-up or request/approval flow in MVP. Only Super Admin can create User/Lab Admin/Super Admin accounts and assign roles. Admin sets a temporary initial password and delivers it through an out-of-band secure channel; never display/store plaintext credentials after creation, and never send them by app notifications. On first successful authentication with this password, require password change **before** granting access to protected application functions. Existing sessions are invalidated or gated when `must_change_password` is true. A new password must satisfy configured minimum password policy, be checked server-side, and be stored only as a salted, strong password hash. The initial one-time Super Admin bootstrap CLI is the only account provisioning exception: read its credentials securely from interactive input or environment and do not expose an unauthenticated setup endpoint. Password reset by Super Admin issues a new temporary credential and re-enables mandatory change. Audit account creation, password reset and role changes without logging secrets.
- User records are disabled rather than deleted if referenced by history.

## 4. Data models (minimum schema)
Use integer PKs; naming constraints/indexes in Alembic. All tables include `created_at` UTC unless already implicit below.

### `users`
`id`, `username` (unique, required), `display_name` (required), `team` (required; e.g. BIOS/BMC/Validation/FW/System), `email` (unique, required), `password_hash` (required), `role` (`user`, `lab_admin`, `super_admin`), `is_active` (default true), `must_change_password` (boolean, default true for admin-created accounts), `password_changed_at` (nullable UTC), `deactivated_at` (nullable UTC), `deactivated_by_user_id` (nullable FK to users), `deactivation_reason` (nullable text), `created_at`.

### `labs`
`id`, `name` (unique, required), `location` (required), `description`, `created_at`.

### `suts`
`id`, `lab_id` FK required, `name` required; `normalized_name` (indexed normalization of trimmed, case-folded name), `UNIQUE(lab_id, normalized_name)` (BR-010; names may repeat across different Labs), `platform` required, `owner_team` required, `description`, `bmc_ip` nullable, `host_ip` nullable, `created_at`, `updated_at`, `is_archived` (boolean, default false, indexed), `archived_at` (nullable UTC), `archived_by_user_id` (nullable FK to users).
- IP fields validated if provided as IPv4/IPv6. **No persisted `status`: effective status is derived**, preventing disagreement among usage, queue, and reservations.
- SUT lab assignment is immutable after creation in MVP (original update list did not include Lab).
- SUT names are manually provided by Lab Admin or Super Admin when registering a SUT; never autogenerated. Trim surrounding whitespace before validation; reject blank names and duplicate names within the same Lab with a friendly form error / API `409 Conflict`. A rename follows the same rule. Treat archived SUT names as still reserved within their Lab, so restoring or historical references never cause collisions; case-insensitive comparison is used for uniqueness (e.g., `SUT-01` and `sut-01` conflict). Implement a normalized-name column or equivalent indexed DB-enforced uniqueness; application-only checking is insufficient.

### `current_usages`
`id`, `usage_key` (stable unique release identity), `sut_id` FK unique (one active usage per SUT), `user_id` FK, `start_time` UTC, `expected_end_time` UTC, `reservation_id` nullable FK, `purpose` (optional user-entered usage purpose); must have `expected_end_time > start_time`.

### `queue_entries`
`id`, `entry_key` (stable unique identity), `offer_generation`, `paused_at` nullable UTC, `remaining_microseconds` nullable integer, `sut_id` FK, `user_id` FK, `requested_duration_minutes` positive integer, `created_at` UTC, `notified_at` nullable UTC, `offer_expires_at` nullable UTC, `offer_status` (`waiting`, `notified`) with default `waiting`; unique (`sut_id`, `user_id`) for active entries. On timeout remove the active entry after writing an `offer_timeout` audit event (including the former entry, user, SUT, offer and expiry timestamps).
- Queue position is **computed** by `created_at, id` ordering (1-based), never a mutable persisted `position`.

### `reservations`
`id`, `sut_id` FK, `user_id` FK, `start_time` UTC, `end_time` UTC, `purpose` required, `status` (`confirmed`, `waiting_for_release`, `claimed`, `cancelled`, `completed`, `no_show`), `created_at` UTC, optional `cancelled_at`, `checked_in_at`, `claimed_at`, `no_show_at`.
- `start_time < end_time`; no overlap among active reservations for the same SUT using half-open intervals `[start, end)`.
- Confirmed reservations that end without a claim are transitioned to `completed` for retention (unless already `no_show`). `no_show` is retained for audit and excluded from availability/conflict checks.

### `usage_histories`
`id`, `usage_key` (unique, copied from current usage), `purpose` nullable, `released_by_user_id` nullable FK, `release_note` nullable text, `sut_id` FK, `user_id` FK, `start_time` UTC, `end_time` UTC, `duration_minutes` nonnegative, `release_reason` (`user`, `admin`) and nullable `reservation_id` FK.
- Completed usages are written exactly once when released, including forced releases.

### `audit_events` (required by confirmed administrative/coordination audit rules)
`id`, `actor_user_id` nullable FK, `sut_id` nullable FK, `event_type`, `details_json`, `created_at`; log administrative force actions, queue changes, reservation changes. Avoid including secrets.

## 5. Explicit scheduling rules (proposed MVP decisions)
These rules resolve conflicts omitted from v1.0. They must be agreed before Codex implements scheduling.

**MVP boundary (confirmed):** This is a coordination and notification system, NOT a hardware/network access-control system. Claim/Release/Queue/Reservation only update app records; they do not lock SUT accounts, block SSH/BMC access, power-cycle a device, or guarantee physical handover. A single `current_usages` entry is a **recordkeeping constraint**, not technical exclusion of actual device access. Conflicts produce explicit warnings and notifications.

**Recorded status is advisory, not a physical-access guarantee.** A recorded `In Use` state means someone has registered themselves as using the SUT. Reminders and conflict flags do not disable access.

**Effective SUT status priority (when operational_state=`normal`):** `In Use` if `current_usages` row exists; else `Reserved` if current time is within any active reservation interval; else `Available`. An upcoming reservation alone does not change current status, but appears in the detail/calendar. Queue presence does not create a fourth status.

**Claim:**
1. **CONFIRMED BR-011:** Authenticated user chooses an expected duration: quick presets 1/2/4/8 hours or a custom positive duration, with **no business maximum**. The UI must support multi-day durations (e.g., 36 or 72 hours), and server-side validation must reject zero, negative, non-numeric or overflow inputs. Expected duration is an estimate, not a hard stop.
2. Reject claim if currently used or now falls in another user's protected reservation window. Before an upcoming reservation, allow temporary use and prominently warn about its time and owner. Recommend ending usage before the reservation starts; do not use technical controls to interrupt access. An expected end time may be adjusted in the UI with user acknowledgement (do not silently enforce a cutoff).
3. If the requester has an active reservation covering now, allow reservation-specific claim and set expected end no later than its reservation end. A reservation is **not** an automatic claim.
4. If a queue exists, direct non-reservation claims are allowed only for the queue head with `offer_status=notified`; after a successful manual Claim remove that queue entry. Do not register usage merely on notification.
5. **CONFIRMED BR-007:** A user may simultaneously Claim multiple **different** SUTs, without a per-user count limit in MVP. Each SUT has its own independent active usage, expected end time, Release and history. One active usage per SUT is enforced; this does not mean one SUT per user. Claim/release authorization is evaluated against the specific SUT usage record.
6. **CONFIRMED BR-011:** Usage does **not** auto-release at expected end in MVP. Overdue usage remains `In Use` until user/admin releases. Display `Overdue` as an additional warning badge (not a replacement for `In Use`) on dashboard, SUT details, and My Usage; show in-app reminders to the owner and clear warnings for upcoming reservations. No hardware/network action occurs. Actual history duration is calculated from real start/release times, not the estimate.

**Release:**
1. Normal release by current holder; force release by authorized admin; repeated release is an error (not duplicate history).
2. Write completed usage history and delete active usage in one transaction.
3. **CONFIRMED BR-004:** When the SUT is recorded as released, notify the FIFO head that it is their turn; update the queue entry to `notified` and set `notified_at`. Do **not** create current usage or remove the queue entry. The SUT remains recorded as Available (unless a reservation window applies) until the notified user manually Claims.
4. Do not offer queue handoff during another user's protected reservation window or while a checked-in reservation holder has priority. Before an upcoming reservation, notify FIFO #1 about the reservation and suggested handoff time. Do not skip the queue head. If the offer is blocked, retain their `waiting` status and show the reason.
5. A queued user who now has an active claim via a reservation is removed from the queue when that claim succeeds.

**Queue:**
- An authenticated user may join once per SUT; cannot join while they own current usage. Require an explicit positive integer requested duration at join time; forms offer an editable 1-hour suggestion, without a silent API default.
- User may leave own queue; admin may clear queue for authorized SUT. Order FIFO (`created_at`, `id`).
- **CONFIRMED (Issue #2 clarification):** Joining queue is allowed when SUT is `In Use` or `Reserved`, or already has queue entries; do not allow joining a truly available SUT with no pending queue (user should claim it).
- FIFO **notification-first promotion** runs on release and when a no-show reservation loses protection, if no active usage exists. Only the notified FIFO head is entitled to manual Claim; successful Claim removes their queue entry and begins current usage. Never skip the head or create two active usages. A no-show must not force-release an existing user.
- **CONFIRMED BR-005:** The notified FIFO head has 15 minutes from `notified_at` to manually Claim. At or after `offer_expires_at`, atomically expire the unclaimed offer, record `offer_timeout` in the audit log, remove the entry from the active queue, show an in-app timeout notice, and notify the next eligible FIFO head with a new 15-minute deadline. A timed-out user may join the end of the queue again. If an active usage or protected reservation blocks allocation, leave the next user waiting and notify once eligible. An explicit Leave Queue advances the queue using the same rules. Run timeout sweeps independently of page visits, idempotently and safely after restart. Concurrent Claim vs expiry must resolve transactionally; never produce double usage or skip a valid on-time Claim. No physical SUT access is controlled.

**Reservation:**
- Any authenticated user can create an advance reservation with future `start_time`, `end_time`, and purpose; **CONFIRMED BR-012:** each reservation must be longer than zero and at most **24 hours (1,440 minutes)**, measured as elapsed time from start to end; **CONFIRMED BR-013:** reservation `start_time` must be no later than **30 × 24 hours** after the server request time (inclusive); `start_time` must be in the future. Evaluate the horizon using UTC instants, present times in Asia/Taipei. A reservation may end after the horizon if its start is within the horizon and BR-012 duration remains at most 24 hours. Reject a longer reservation in both API and HTML with a clear validation error; never silently truncate it. A 24-hour reservation is permitted; BR-011 Claim estimates are not capped by this rule.
- Reject invalid past start/end and overlapping confirmed/claimed reservations on the same SUT. If recorded current usage is expected to extend beyond the requested reservation start, show a conflict warning at booking time and flag the reservation as at-risk; do not assume the application can revoke actual access. Overlapping **reservation-to-reservation** windows are still rejected.
- Existing active usage may become overdue after booking and will NOT be forcibly preempted. UI warns that reservation availability may be delayed.
- **CONFIRMED BR-014:** A user may edit or cancel **their own not-yet-started reservation**; Lab Admin (across both labs) and Super Admin may edit/cancel any not-yet-started reservation. Edit supports start_time, end_time, and purpose (and retains the same SUT and owner). An edit must revalidate BR-012 (duration > 0 and <= 24 hours), BR-013 (new start after current server time and within 30 days), and reservation overlap; persist only after successful validation in a transaction. Reject edits to started, claimed, checked-in, no-show, completed, or cancelled reservations; do not silently move or truncate dates. Cancellation soft-transitions to `cancelled`, preserving audit/history; do not hard delete. On cancellation, release the reservation priority and re-evaluate queued offers as appropriate. Use 403 for forbidden actor and 409 for incompatible reservation state/overlap (422 for invalid time input).
- **CONFIRMED BR-002: 15-minute no-show grace period.** A reservation owner must click `Claim` or `I'm here / Check in` by `start_time + 15 minutes`. When the SUT is free, `Claim` creates the recorded current usage and sets the reservation `claimed`. If the user presses `Check in` instead, record attendance; display an explicit Claim action before creating a usage. If an earlier user is still recorded as occupying it, `Check in` sets reservation `waiting_for_release` (with `checked_in_at` timestamp); it does **not** create a second current usage and is **not** counted as no-show. A reservation still `confirmed` with no check-in at its deadline is marked `no_show` (audited) and ceases to reserve priority. A periodic idempotent worker applies no-show transitions independent of page visits. Neither reaching a booking boundary nor checking in can forcibly disconnect any real SUT user.
- **CONFIRMED BR-003: Check-in while occupied (option B, advisory implementation).** Display `Reservation holder checked in — awaiting recorded release` and notify the temporary user that the reserved slot has begun. On recorded release, prefer the checked-in reservation over FIFO queue; show the SUT as available for that checked-in reservation holder to Claim and send an in-app notice. Do not create a `current_usages` row for the reservation holder automatically. Queue entries remain intact, and unrelated users must not bypass the checked-in reservation while it has priority. Keep Queue order for subsequent handoffs. If the prior holder never records Release, keep the discrepancy visible and auditable; admin can coordinate manually. Define any later abandonment timeout separately (not part of MVP).
- `waiting_for_release` is a reservation workflow state, not a SUT hardware lock. Include `checked_in_at`; do not conflate `Claim` with check-in. Any alerts in MVP may be in-app banners/status indicators; external push messaging is future scope.
- Calendar displays confirmed, claimed and historical reservations distinctly, including `no_show` as an audit state; confirmed/checked-in/claimed entries drive calendar priority and warnings, not hardware access controls.

**Concurrency / data integrity:**
- Claim, release, queue promotion, reserve, cancel and queue joining must be atomic and re-check business constraints in the write transaction.
- SQLite MVP single application worker, serialize contested writes with SQLite `BEGIN IMMEDIATE` (or equivalent) and handle `database is locked` with bounded retry/error. Add uniqueness constraints where applicable. Do not assume `SELECT FOR UPDATE` works on SQLite.
- Automated tests must include contention/double-claim behavior; two simultaneous successful claims of the same SUT are never allowed.


### CONFIRMED BR-015 — Extend estimated SUT usage (advisory)
- The current usage owner may change the `expected_end_time` of their own active usage directly, without Release/re-Claim. Lab Admin and Super Admin may make an administrative adjustment; all changes are audited.
- New `expected_end_time` must be later than the server's current time and later than `start_time`; it is not capped at 8 or 24 hours (BR-011). The actual usage start and usage record ID are unchanged. Do not create usage history when adjusting the estimate.
- If the proposed extension overlaps any other user's active/upcoming reservation, return explicit conflict details to the UI and require a separate affirmative acknowledgement before saving. Overlap is a **warning**, not a denial, and no reservation is modified or cancelled. JSON API requires `acknowledge_reservation_conflict: true` to persist such a conflicting change; without it return `409` with a stable `reservation_conflict_confirmation_required` code and conflict summary. If no overlap, acknowledgement is unnecessary.
- Use an atomic update that rechecks ownership, current active usage, reservation overlaps and acknowledgement. Record old/new end time, actor, timestamp and acknowledged conflict in audit history; show the new estimate and existing booking warnings on detail/dashboard/calendar where applicable.
- Only the registered current owner or an authorized admin can extend the recorded usage; an unauthorized user receives 403 and a missing/inactive usage receives 404/409 as appropriate. No SUT/network access restrictions or automatic Release are introduced.

### CONFIRMED BR-016 — No direct usage handover (Release then Claim)
- The MVP must **not** implement direct holder-to-holder transfer, reassignment, or a handover endpoint/button.
- When Kevin wishes Charlie to use the same SUT, Kevin performs the normal Release; the completed usage history is preserved. Charlie must perform a separate manual Claim when eligible, creating a new active usage record with Charlie's own start time and expected end time.
- On Release, **BR-003/004/005 still apply**: notify a checked-in reservation holder with priority or the eligible FIFO queue head; do not automatically register Charlie as current user. If Charlie is not next in line, Release does not let Kevin bypass existing priority on Charlie's behalf.
- This workflow updates system records and reminders only, never physical SUT access. Audit Release and Claim as distinct operations.

## 6. Functional pages
| Page | Route | Contents |
|---|---|---|
| Login | `/login` | Sign in / sign out |
| Dashboard | `/` | Total Labs, Total SUTs, Available/In Use/Reserved, labs and SUT summaries |
| Labs | `/labs` | List and admin create/edit/delete |
| SUT list | `/suts` | Search, filters, statuses, pagination |
| SUT detail | `/suts/{id}` | Info, holder/times, queue, reservations, context-aware actions |
| Calendar | `/calendar` | SUT reservation calendar by day/week, timezone label |
| History | `/history` | Completed usage, filters by user/SUT/date, pagination |
| Admin | `/admin` | Admin links, user management for super admin, authorized inventory actions |

Use `base.html`, reusable navbar/sidebar/flash-message partials, consistent Bootstrap UI, accessible forms, CSRF protection, friendly HTML 403/404/validation states, responsive layout.

## 7. HTTP API contract
Base prefix `/api/v1`. Use session-based authentication for MVP. JSON errors with stable `{ "detail": "..." }` and appropriate 400/401/403/404/409/422 codes. API mutation requests must be protected from cross-site requests (CSRF token or equivalent origin enforcement). Never trust user IDs supplied in claim/queue payloads.

| Method | Route | Access | Notes |
|---|---|---|---|
| GET | `/labs` | Authenticated | Paginated list |
| POST | `/labs` | Lab Admin/Super | Role-based authorization (all labs) |
| PUT | `/labs/{id}` | Lab Admin/Super | Role-based authorization (all labs) |
| DELETE | `/labs/{id}` | Lab Admin/Super | 409 if SUTs exist |
| GET | `/suts` | Authenticated | `page,page_size,search,lab_id,platform,owner_team,status` |
| GET | `/suts/{id}` | Authenticated | Full detail |
| POST | `/suts` | Lab Admin/Super | Role-based authorization (all labs) |
| PUT | `/suts/{id}` | Lab Admin/Super | No lab move in MVP |
| DELETE | `/suts/{id}` | Lab Admin/Super | **BR-009:** archive (never hard delete); 409 if active usage, active queue entries, or future/ongoing reservations |
| POST | `/suts/{id}/restore` | Lab Admin/Super | **BR-009:** restore archived SUT; reject duplicate active operation |
| POST | `/suts/{id}/claim` | Authenticated | `{ "duration_minutes": 240 }`; 409 on conflict |
| PATCH | `/suts/{id}/usage/expected-end` | Holder/Admin | **BR-015:** `{ "usage_key": "current stable key", "expected_end_time": "ISO-8601 with offset", "acknowledge_reservation_conflict": false }`; request acknowledgement on reservation overlap; audit the adjustment |
| POST | `/suts/{id}/release` | Holder | `{ "usage_key": "current stable key", "reason": "optional" }`; history + promotion summary; admins use audited force-release for others |
| POST | `/suts/{id}/force-release` | Lab Admin/Super | `{ "usage_key": "current stable key", "reason": "required" }`; audited |
| GET | `/suts/{id}/queue` | Authenticated | FIFO with derived position |
| POST | `/suts/{id}/queue` | Authenticated | `{ "requested_duration_minutes": 60 }` |
| DELETE | `/suts/{id}/queue` | Queued user | `{ "entry_key": "current stable key" }`; leave own entry, stale retries cannot remove a rejoined entry |
| DELETE | `/suts/{id}/queue/all` | Lab Admin/Super | `{ "reason": "required" }`; audit action |
| GET | `/reservations` | Authenticated | Filter `sut_id`, dates |
| POST | `/reservations` | Authenticated | ISO-8601 timezone-aware start/end, purpose |
| PUT | `/reservations/{id}` | Owner/Admin | **BR-014:** edit future confirmed reservation start/end/purpose; revalidate BR-012, BR-013 and overlap |
| DELETE | `/reservations/{id}` | Owner/Admin | **BR-014:** cancel own / any admin-managed future confirmed reservation; retain record |
| GET | `/history` | Authenticated | Pagination, user/SUT/date filters |
| GET | `/users` | Super Admin | Paginated |
| POST | `/users` | Super Admin | Create account with initial temporary password; force password change at first login (BR-020) |
| PATCH | `/users/{id}/status` | Super Admin | Disable/reactivate an account (BR-021); must not deactivate final active Super Admin |
| PATCH | `/users/{id}` | Super Admin | Update role/active state |
| POST | `/users/{id}/reset-password` | Super Admin | Set a new temporary password; require change at next login |
| POST | `/auth/change-password` | Authenticated | Current/new password; required on first login; no access to other protected functions until changed |
| GET | `/health` | Public | Return `{"status":"ok"}` |

The documented API paths above are relative to `/api/v1`, except `/health`. Document request/response schemas in OpenAPI generated by FastAPI. Browser form routes may differ but must use the same service logic.

## 8. Deletion and history integrity
- Labs: delete only when no SUTs.
- **CONFIRMED BR-009:** `DELETE /suts/{id}` means **archive** for every SUT, regardless of whether it has history; there is no hard-delete API for SUT in MVP. Require no active usage, no active queue entry/offer, and no confirmed/checked-in ongoing or future reservation. If blocked return `409` with an actionable message. Do not silently cancel bookings, queue entries, or usage to archive.
- On archive set `is_archived=true`, `archived_at` UTC, `archived_by_user_id`, and write an audit event. Archived SUTs are absent from default dashboard/KPIs/normal inventory, searches, queue/claim/reservation workflows; historical usage and reservation records remain readable with the archived SUT name. Admin inventory can use `include_archived=true` to find them.
- Admin may restore an archived SUT, clearing archive metadata and recording an audit event. Restore does not revive expired queue offers, usages or reservations. Archived SUTs may not accept new claims, reservations or queue entries until restored. Archive/restore are transactional/idempotent (repeated action should not corrupt data); test both lab admins and super admins.
- Never cascade-delete usages or history when deleting records.

## 9. Nonfunctional requirements
- `docker compose up --build` starts one web worker, with persisted `./data` volume (or named volume) and app listening inside the container at `0.0.0.0:80`, published on host port `5088`.
- `.env.example` documents non-secret configuration; `.gitignore` ignores `.env`, SQLite files, venv, caches.
- Alembic initial migration creates full schema; no `Base.metadata.create_all()` at app start.
- Bootstrap admin CLI, deterministic demo seed script (development only), pytest with isolated temporary DB, explicit migration/test commands.
- Logging includes request IDs and business errors but never passwords, session secrets or sensitive authentication material.

## 10. MVP definition of done
1. All routes work with server-side authorization; unauthorized writes are rejected.
2. Full Lab/SUT CRUD constraints verified.
3. Exactly one active user per SUT, while the same user may hold multiple distinct SUTs (BR-007); each SUT claim/release creates and closes its own record and writes history once.
4. FIFO queue prevents duplicate join; release notifies the queue head but does not mark them In Use until manual Claim. An unclaimed offer expires after 15 minutes, is audited, and proceeds to the next eligible user without violating reservation priority.
5. Active reservations do not overlap one another; when existing usage may conflict with a new booking, warn and flag it at-risk rather than block the booking solely on self-reported usage.
6. Dashboard, detail, calendar and history show correct status and timestamps.
7. Migration works on empty DB; data survives Docker container recreate.
8. Automated tests for role enforcement, conflicts, expired expected time, competing claim requests, queue order, reservation overlap and delete constraints pass.
9. `docker compose up --build`, `alembic upgrade head` and `pytest` commands are verified or explicitly marked unverified with blocker descriptions.

## 11. Decisions to confirm before scheduling implementation
1. CONFIRMED BR-008: Lab Admin can manage all labs and SUTs, create/delete labs, force-release and clear queues across both labs; Super Admin alone manages users and configuration. No `lab_admin_assignments` table.
2. CONFIRMED (clarified): FIFO #1 may temporarily use the SUT before a reservation; actively warn about the upcoming reservation, but no hardware cutoff or forced release.
3. CONFIRMED: reservation owner manually clicks Claim; no-show grace is 15 minutes, then reservation becomes `no_show` and its block is removed.
4. CONFIRMED BR-003: reservation holder checking in during the grace period while a prior user is still recorded as active enters `waiting_for_release`; not a no-show; prior user is notified; manual Claim after release; no forced release or hardware access restriction.
5. CONFIRMED BR-004: notify FIFO #1 on release; no automatic usage creation; FIFO #1 manually Claims. BR-005 confirmed: notified FIFO head gets 15 minutes to Claim, otherwise their offer expires, is audited, and the next eligible user is notified.
6. CONFIRMED BR-006: Taiwan-only; all displayed/input times are Asia/Taipei; UTC at rest.
7. CONFIRMED BR-009: SUT deletion always archives, no hard deletion, history retained, admin restore allowed. CONFIRMED BR-010: Admin manually names each SUT on registration; names must be unique within a Lab (including archived SUTs), but the same name may occur in different Labs; uniqueness is case-insensitive after whitespace trimming.
8. **BR-011 confirmed:** No maximum for Claim expected duration. **BR-012 confirmed:** each advance reservation lasts at most 24 hours (elapsed time); **BR-013 confirmed:** advance booking start is at most 30 days from submission.
9. CONFIRMED BR-007: one user can hold multiple distinct SUTs simultaneously; each SUT has an independent usage and history record. No per-user maximum in MVP.


## BR-017 — Maintenance and Out of Service (Confirmed; Option B)

For the Taiwan-only, ~20-SUT MVP, Lab Admin and Super Admin can set an operational availability flag to `normal`, `maintenance`, or `out_of_service`, with a mandatory reason when not `normal`. These are **administrative coordination states only**: do not connect to or disable physical SUT hardware, BMC, SSH, or network access.

- Data: add `operational_state` (default `normal`), `operational_reason` (nullable text), `operational_updated_at` (UTC), `operational_updated_by_user_id` (nullable FK). Audit old/new state, reason and actor; preserve state across app restarts.
- Show a prominent `Maintenance` or `Out of Service` status (with reason) on Dashboard, inventory, SUT Detail and Calendar. For current recorded usage, also show the current user and `In Use` as a secondary indicator rather than hiding an existing claim; mark a visible conflict. `Overdue` remains an independent indicator.
- While either non-normal state is active, reject **new** Claim, Queue join and Reservation creation (API `409`, friendly UI); disable their buttons. Apply the same check transactionally when promoting/notifying Queue offers and when claiming from an existing offer/reservation. This restricts *application registration*, never physical access.
- Do not silently force-release an active usage, delete existing queue entries, cancel existing reservations or erase history when the state changes. Warn admins about outstanding activity before confirming the status change; flag affected reservations and queue records, pause queue offers (with explicit handling of existing offer deadlines), and show their holders an in-app notice. Existing users can still Release or leave Queue; administrators can clear Queue. Returning to `normal` resumes eligibility/re-evaluates any pending queue offers against valid reservations; do not resurrect expired offers.
- API: `PATCH /api/v1/suts/{id}/operational-state` with `{ "state": "maintenance" | "out_of_service" | "normal", "reason": "..." }` (admin only). Require nonempty reason for non-normal states; `normal` clears the active reason but retains audit history.
- Tests: role guard, state persistence and display, reason required, block new actions in both states, maintenance during active usage/reservations, release still works, restoration to normal re-evaluates queue without duplicate notification and without bypassing a checked-in reservation.


## BR-018 — Automatic status and notification refresh (Confirmed; Option B)

- Dashboard (`/`), SUT Detail (`/suts/{id}`), and in-app notification area automatically refresh their **displayed status every 30 seconds** while the page is open. Use lightweight HTTP polling, not WebSocket/SSE, for the MVP.
- Supply authenticated JSON read endpoints (or appropriate existing GET endpoints) returning current SUT status, current recorded usage, queue/offer, upcoming reservations, operational condition, and unread notifications as appropriate. Apply normal view permissions and avoid exposing sensitive fields.
- Display last successful refresh time and a subtle stale-data / retry indicator on failure. A failed request must not clear or falsely overwrite existing status; retry on the next interval.
- Polling is **read-only**: never Claim, Release, consume a queue offer, mark a notice read, or change records just because a page refreshes. Existing backend background jobs and transactional endpoints remain responsible for queue offer / no-show expiry.
- After a user submits a successful action, refresh relevant parts immediately; the periodic interval is the fallback for changes by others. Polling must not erase unsaved form edits, reset search/filter position, or duplicate notification banners.
- Tests: verify 30-second interval configuration, fresh state appears without manual browser reload, permissions, offline/error fallback, no duplicate messages or mutation side effects; use browser/JS tests where practical. No real-time delivery guarantee: changes may appear up to roughly 30 seconds later while page is open, plus network latency.


## BR-019 — MVP notification channels (Confirmed; Option B)

- MVP channels: **persistent in-app notifications** (notification bell/list, unread count, read/unread state) and **optional browser desktop notifications** using the browser Notification API. Email and Microsoft Teams integrations are **future enhancements only**; no SMTP, Teams OAuth, webhooks, or outbound messaging required for MVP.
- Relevant events include: Queue offer/next user and expiry (BR-004/005), reservation upcoming/starting, reservation no-show, conflicting active usage or upcoming reservation, usage overdue, and SUT maintenance/out-of-service warnings. Avoid generating repeat notifications for the same recipient and event transition.
- In-app notifications MUST be persisted server-side, scoped to the signed-in user, shown on Dashboard/SUT Detail notification area and accessible via a notification bell. Support marking notifications read via explicit authenticated POST/PATCH; read-only polling MUST NOT mark messages read. Poll unread updates every 30 seconds per BR-018; show timestamps in Asia/Taipei.
- Browser notifications are **opt-in**. Request browser permission only after a user gesture (e.g., `Enable desktop notifications` button), never automatically on login or page load. If permission is denied, unavailable, or unsupported, continue in-app notifications without errors.
- Desktop notifications are best-effort **only while the site remains open in a supported browser context**. Do not implement service workers/web push/background delivery in MVP, and do not promise alerts after closing all site tabs. The Notification API may require HTTPS (or localhost in local development) and may be blocked by browser/OS settings. Provide a clear UI explanation.
- Prevent duplicate desktop alerts across successive 30-second polls for the same notification ID (persist per-tab/session delivery state or equivalent). An alert should link/focus the appropriate page when browser capabilities allow; avoid leaking passwords or secrets in notification text.
- API: authenticated GET `/api/v1/notifications?unread_only=true` and PATCH `/api/v1/notifications/{id}/read` (or functionally equivalent documented endpoints). Only the recipient may read or mark their notifications. Store notification ID, recipient, event type/reference, message, created_at UTC, read_at UTC nullable.
- Tests: authorization/no cross-user access; event creates exactly one persisted notification even if retries occur; unread counts and read action; 30-second polling is read-only; opt-in permission handling, denied/unsupported fallback, no duplicate desktop alerts, and browser-closed delivery is not claimed.


## BR-020 acceptance tests — administrator-provisioned accounts
- No public registration page or endpoint; anonymous requests and non-Super Admin create/reset requests are denied.
- First Super Admin can be provisioned via CLI without hardcoded secrets; no bootstrap route is exposed.
- Super Admin creates an account with temporary initial password; database stores only its hash and sets `must_change_password=true`.
- First login redirects to mandatory change-password page; API requests for normal business actions are blocked until password is updated.
- After successful password change, the flag is cleared and normal role permissions apply. Wrong current password / weak new password / unauthorized role changes are rejected.
- Super Admin password reset forces password change on the next login; audit records contain no plaintext passwords.

## BR-021 — Deactivate accounts without automatically changing resource records (Confirmed; Option B)

- Only Super Admin may deactivate/reactivate user accounts; never hard-delete users referenced by usage, reservations, queues or audit history. Deactivation sets `users.is_active=false` and records `deactivated_at`, `deactivated_by_user_id`, optional reason, and an audit event.
- Disabled users cannot sign in; previously issued sessions must be invalidated or rejected on subsequent authenticated requests. Reject their authenticated API mutations, including Claim, Release, Queue, Reservation, and notification mark-read; normal role checks still apply.
- Before confirmation, show a resource-impact summary listing the user's active usages, active/waiting queue entries and upcoming valid reservations, with SUT and Lab names. After deactivation, surface these items in an Admin `Needs attention` view (count + drill-down links).
- **No automatic Release, Queue removal, Reservation cancellation or physical device action** on deactivation. Existing records remain linked to the disabled account, and usage/history remain auditable. A disabled user cannot Claim when offered a queue slot.
- Lab Admin/Super Admin may force-release recorded usages and clear queue entries under their existing powers; Super Admin may cancel/edit eligible upcoming reservations per BR-014. Preserve all cancellation/release reasons and actor in audit trails.
- When offering a queue position, skip temporarily ineligible inactive users without deleting their queue record, record the skip and notify the next eligible user. A disabled user's pending offer must not block others; expire/invalidate that offer without treating it as a voluntary Claim. Do not silently erase the underlying entry.
- The 15-minute no-show/offer deadlines and reservations must continue their normal server-side lifecycle. While a disabled account has upcoming bookings, the Admin view keeps showing them until an authorized admin resolves them or the normal no-show/completion state ends them.
- APIs: Super Admin-only `PATCH /api/v1/users/{id}/status` accepting `is_active` and optional `reason`; authenticated Super Admin impact preview and listing of disabled-user unresolved resource records (exact read-route names documented in API contract). Reject disabling the **last active Super Admin** to avoid lockout.
- Acceptance tests: deactivation permissions, forced session invalidation, no automated modifications to usage/queue/reservation records, impact summary completeness, admin manual cleanup with audit, last-active-super-admin safeguard, inactive queue-user nonblocking logic, reactivation, and preservation of history.

## BR-022 — Visible colleague contact details for coordination (Confirmed; Option C)

- **Authenticated** active users (User, Lab Admin, Super Admin) may view the recorded current user, queue participants and reservation holders on SUT views, including **display name, team, work email, expected/reserved times and usage/reservation purpose where supplied**. Queue views must not invent a purpose where none was entered.
- Show work email as a `mailto:` link for easy RD coordination; do not expose password hashes, security/session fields, or administrative/private account metadata. Display only relevant minimum coordination details, not the entire user record.
- Anonymous visitors must not see these views or access contact details via API. Disable unauthenticated caching/indexing and require server-side authorization for all HTML and API response paths including 30-second polling endpoints.
- Add `users.team` as a required team field to admin-provisioned user accounts; this is distinct from `suts.owner_team`. Optionally collect `current_usages.purpose` during Claim for the active-use purpose; do not force migration backfill guesses. The existing reservation `purpose` remains required.
- Existing historical entries remain attributable to the same user even when their account is disabled. Provide reasonable display for accounts without a team during migration until backfilled. Do not expose emails in browser desktop notifications by default.
- Tests cover authenticated cross-user visibility of work email/team/purpose, anonymous denial, hidden sensitive fields, queue/reservation display, and persistence after account deactivation.

## BR-023 — Self-service user profile management (Confirmed: Option B)

- Authenticated active users may edit **only their own** `display_name`, `team`, `email`, and password from a dedicated Profile page (`GET /profile`, `POST /profile`, and a separate password change form). The account `username`, `role`, `is_active`, `must_change_password` and other security/administrative fields are not user-editable. Only Super Admin may administer roles and account status under BR-020/021.
- Expose authenticated `GET /api/v1/users/me` and `PATCH /api/v1/users/me` for an allowlisted profile payload (`display_name`, `team`, `email` only). Existing `POST /api/v1/auth/change-password` handles password updates, including first-login mandatory change. Do not add a self-service user-ID update endpoint.
- Validate required nonblank display name/team, normalized valid work email and case-insensitive unique email across accounts; return clear validation/conflict errors in both UI and API. Do not let profile updates circumvent `must_change_password`: before first change, only authentication/logout and password-change functions are available.
- For a voluntary password change after onboarding, verify current password, enforce configured password policy, rotate/invalidate other sessions, and never expose plaintext password or hashes in UI/API/logs. Updating profile details does not change role, username or authentication status.
- Audit changes with actor/user ID and timestamps, recording previous/new profile fields as needed while never logging passwords or other credentials. Show updated display name/team/email on relevant SUT/Queue/Reservation pages after refresh (BR-018/022).
- Tests: self update success; cannot update others; mass-assignment of role/username/active rejected; duplicate or invalid email rejected; normal and first-login password-change controls; session invalidation after password change; history remains linked by user ID.


## BR-024 — Usage History retention (Confirmed: Option A)

- Usage History records are retained indefinitely by application policy. No time-based expiration, cleanup scheduler, TTL, purge endpoint, or scheduled deletion of usage histories is permitted in MVP.
- Preserve user/SUT associations and original start/end timestamps and actual usage duration after SUT archival (BR-009), user deactivation (BR-021), or profile edits (BR-023).
- Users may query history through existing authenticated filters (SUT/user/date) and pagination; these are non-destructive read operations.
- Normal Release and Admin Force Release close the active usage and create/preserve the history record atomically; retries must not create duplicate history.
- Do not cascade-delete history on user/SUT changes. Database backups, storage capacity, and disaster recovery remain separate operational concerns; indefinite retention is not a guarantee against loss without backups.
- Acceptance: create and close a usage, archive its SUT and deactivate its user, then verify the history remains retrievable; no scheduled purge exists; listing/filtering never deletes entries.

## BR-025 — Dashboard Card/Table View Toggle (Confirmed: Option C)
- Dashboard `/` MUST default to **Card view**, grouping roughly 20 SUTs by Lab. Each card shows SUT name, Lab, platform, effective availability/maintenance status, recorded current holder, expected end time, next reservation summary, and link to detail. Never show secrets.
- Users MAY toggle between **Card** and **Table** views without a full-page reload. Table columns MUST include Lab, SUT name, platform, effective status, current holder, and expected end time; SUT name links to detail.
- Both views MUST use the **same filtered/sorted data source** and share Lab, platform, SUT name, owner team, and status filters. Toggling MUST NOT reset filters/search or change the set of SUTs being shown. Provide an accessible Card/Table toggle, correct labels, and responsive layouts.
- The default for a new visit is Card; retaining the selection in the current browser session is allowed but not required for MVP. Do not build separate business logic for each view.
- BR-018 30-second read-only HTTP polling MUST refresh the **currently visible view** and KPI totals without resetting filters, selected layout, scroll unnecessarily, or unsaved form inputs. Display last refresh/stale-state feedback on network errors.
- Archived SUTs are excluded from ordinary Dashboard and KPI totals (BR-009); Maintenance and Out of Service remain visible with reasons (BR-017). The effective status and secondary flags (such as Overdue) must be consistent across both views.
- Add automated tests for initial Card rendering, toggle behavior, consistent filtered results across views, and polling updates in either view.


## BR-026 — Dashboard reservation visibility per view (Confirmed: custom Card + Table)
- BR-025 remains unchanged: Dashboard defaults to **Card view** and permits switching to **Table view**, using the same SUT inventory/search/filter/status source.
- **Card view:** each SUT card displays **only the next upcoming valid reservation**: reserver display name and reservation start/end in Asia/Taipei; show “No upcoming reservation” if none. Sort by start time, exclude cancelled, no-show, completed/expired reservations. Do not show multiple future bookings on a card.
- **Table view:** for each SUT show **all valid reservations overlapping the rolling next 24 hours**, from current server time `now` to `now + 24 hours`, in chronological order. Show reserver and reservation start/end (Asia/Taipei); include bookings spanning either boundary and indicate their full booked times, not a clipped interval. If none show “No reservations in next 24h”. This is **not** a calendar-day cutoff at midnight.
- Effective overlap predicate is `reservation.start_time < window_end AND reservation.end_time > now`, restricted to active/confirmed bookings and any appropriately checked-in active reservation; do not show cancelled/no-show/completed bookings. A reservation that started earlier but still occupies part of the 24-hour window is included in Table view.
- Both layouts retain SUT status, holder, maintenance/overdue warnings and links to detail; Table view must not hide columns due to reservation list length. Use an expandable or wrapped reservation cell for clarity.
- BR-018 30-second read-only polling refreshes the reservation summaries for the selected layout without resetting filters, selected layout, or user input. The backend provides consistent results under server time; no frontend-only local-time window calculation.
- Acceptance: cards show exactly one next upcoming booking, tables show zero/one/multiple bookings within a rolling 24h interval including boundary overlaps, no bookings outside, and state changes are reflected by polling. Test Taiwan time formatting and cancelled/no-show exclusions.

## BR-027 — Dashboard quick actions (Confirmed: Option B)
- Dashboard Card and Table views MUST provide contextual quick actions for **Claim**, **Join Queue**, and **Reserve**, using accessible Bootstrap 5 modal dialogs without navigating away from Dashboard. Preserve the BR-025 Card-default toggle and BR-026 reservation summaries.
- Claim modal: show selected Lab/SUT, editable expected duration (1/2/4/8 hours or custom), optional usage purpose, current holder/queue offer and any upcoming reservation conflict warning. Reuse the existing authenticated claim service/API and BR-011/015 warning-and-confirmation semantics; never imply the interface blocks physical hardware access.
- Join Queue modal: show the selected SUT and current queue/position when available; prevent duplicate queue entries; reuse existing FIFO/offer/timeout rules BR-004/005. For users already queued, show their current position and a link to SUT Detail rather than submitting a duplicate request.
- Reserve modal: show selected SUT, start/end in Asia/Taipei and required purpose; enforce existing reservation validations including BR-012 (<=24h), BR-013 (start no more than 30 days ahead), overlapping bookings, maintenance state and permission checks. Show validation errors inside the modal.
- Both views MUST offer the same action capabilities; actions available in UI depend on user role, device condition, and server-reported state. Disabled/hidden UI buttons are not security: ALL APIs must recheck authorization and current resource state atomically. BR-003/004 priority and queue/reservation coordination rules continue to apply.
- After a successful modal action, close the modal, show a single success message, and immediately refresh the relevant SUT, KPI and reservation/queue display; retain active Card/Table view, filters, search and user scroll position. On API/network failure, keep the modal open with user-entered values and an actionable error.
- BR-018's read-only 30-second polling MUST NOT overwrite an open modal, pending form fields, selected SUT, or result messages. Debounce/disable submission while pending to prevent duplicate Claim/Queue/Reservation records.
- Keep SUT Detail page as the full-information path, accessible from both Dashboard modes. No SPA framework, WebSocket, device control, or new business rules are introduced.
- Acceptance: modal opens with correct SUT in both modes; form/API validation matches detail flow; duplicate queue, conflicts and concurrent claims are handled; successful changes refresh immediately; no submitted duplicates; polling preserves open modal and filters; access controls enforced server-side.


## BR-028 — Dashboard sorting (Confirmed: customized option C)
- The Dashboard MUST provide exactly two user-selectable sort keys: **Name** and **Status**. Default is **Name ascending**. No Platform, Expected End Time or configurable admin display-order sort in MVP.
- Both Card and Table use identical sort choice, independent of view, and preserve it when toggling views, filtering, searching, and every 30-second HTTP polling refresh.
- Keep SUTs grouped by Lab; sort **within each Lab**, not across labs. Name sort uses case-insensitive natural ordering (e.g., SUT-2 before SUT-10), with SUT ID as stable tie-breaker.
- Status sort orders **Available, Reserved, In Use, Maintenance, Out of Service**, followed by name ascending and ID as tie-breakers. `Overdue` is an In Use indicator, not a separate primary state. Archive exclusions and effective-status derivation are unchanged.
- The sort dropdown must clearly label `Name` / `Status`, be keyboard accessible, and be preserved for the current user during page navigation when practical (localStorage or query parameter; no new database column required).
- Test both modes, status ranking, natural name ordering, lab grouping, filtering, 30s polling, and stable ties.

## Delivery acceptance clarification — Full MVP, three-day target
The approved deliverable is ALL confirmed BR-001–BR-028, including background deadlines, notifications, admin/profile workflows, both Dashboard modes and sorting. No BR may be silently removed to fit a three-day timebox. Completion requires successful tests, documented security/concurrency checks, fresh migrations, reproducible Docker deployment and usable UI; extend execution beyond Day 3 if needed. `SPRINT_3DAY.md` is sequencing only, not a change to business scope.

## DEP-001 — Internal LAN Docker Deployment (confirmed)

- Target: a single internal Linux Docker host, example private LAN address `10.88.26.99`, browser URL `http://10.88.26.99:5088/`. Address is an example configurable deployment target, not a fixed application constant. Not a claim the host is accessible or configured.
- MUST supply root-level `Dockerfile` (or documented `backend/Dockerfile` with correct build context) and `compose.yaml`; publish TCP `5088:80` by default (overridable via `APP_PORT`, e.g. `${APP_PORT:-5088}:80`). App binds `0.0.0.0:80` inside container; `/` is the application/login page, `/health` returns 200 on healthy startup.
- **Deployment artifacts:** Dockerfile and Compose alone are NOT sufficient. Default **production** method is Compose with a remote Git build context, which fetches application source during image build; the server stores only compose.yaml and locally configured secrets (plus Docker named volume). The Dockerfile and application source remain in GitHub. Never clone at container startup.
- Keep SQLite at `/app/data/sut.db`, persist with host bind `./data:/app/data` or named volume; never bake SQLite DB, passwords, or mutable user files into the image. Use `.env.example`; never commit actual `.env`. Explain filesystem permissions, volume ownership, backup and restore.
- Configure one app worker and one effective background scheduler for expiration processing (BR-002/005). Avoid duplicate schedule execution on restarts. Run `alembic upgrade head` before service accepts traffic; errors must fail startup visibly. Do not run `create_all()` during app startup.
- Provide complete server steps: install Docker Engine/Compose plugin and Git remote-context build support; place `compose.yaml` and locally generated `.env` on host; configure secure admin bootstrap; `docker compose up -d --build`; `docker compose ps`; `docker compose logs -f`; test `curl http://localhost:5088/health` on server and `http://<server-ip>:5088/` from a LAN browser. Document updates, migrations, backup/recovery, and restart persistence.
- Host must permit TCP 5088 inbound from authorized LAN clients. Container port publishing cannot fix VLAN routing or OS/network firewall rules. Bind to LAN-facing interface and recommend limiting access to trusted internal networks; never expose admin tools or secrets on a public interface.
- **Browser notifications caveat:** BR-019 in-app notifications and HTTP polling MUST function over internal HTTP. Browser desktop Notification API may be unavailable because a private-IP `http://` URL is not a secure context. Provide graceful fallback plus an explicit UI message. An HTTPS internal hostname and trusted certificate are required if desktop notification support must be dependable; do not quietly mark that secure-context requirement as passing over plain HTTP.
- Required tests: Compose syntax/build, fresh SQLite migration, `/health`, authenticated UI via published port, two client sessions on LAN, data survives `docker compose down` (without `-v`) and restart/rebuild, timeouts process without open browser, local HTTP desktop-notification fallback explained, and firewall/network prerequisites documented. Running the suite in an agent environment does not itself verify access to the real `10.88.26.99` server.


## DEP-002 — GitHub Remote Build (approved production deployment)

> DEP-007 supersedes this as the primary operator path. The Remote Build instructions are retained for optional developer/alternative deployment.

- **Production preference:** On Linux host `10.88.26.99`, deploy using only a `compose.yaml` file and locally generated runtime secrets/configuration (`.env` if needed). Do NOT require copying/cloning the entire source repository onto the server. The application source and root `Dockerfile` live in GitHub.
- `compose.yaml` MUST support a remote Git build context. Example for a public repo (replace placeholders and PIN a release tag or full commit SHA for repeatability):

```yaml
services:
  sut-management:
    build:
      context: https://github.com/YOUR-ORG/sut-management-system.git#v1.0.0
      dockerfile: Dockerfile
    ports:
      - "${APP_PORT:-5088}:80"
    environment:
      DATABASE_URL: sqlite:////app/data/sut.db
      TZ: Asia/Taipei
    volumes:
      - sut-data:/app/data
    restart: unless-stopped
volumes:
  sut-data:
```

- `Dockerfile` MUST copy/build application code into the image; startup runs migrations safely and serves FastAPI on `0.0.0.0:80`. **Do not run `git clone`, `git pull`, or install Git credentials inside the running container.**
- The server needs Docker Engine + Compose plugin, Git/BuildKit support for remote Git build context, outbound GitHub access, and appropriate authentication if the repo is private. Never write tokens into Compose, Git URLs, Dockerfile or repository. Document safe authentication via host-side Git credential/SSH support and verify chosen builder actually supports it.
- Use a Docker named volume for SQLite. Preserve the volume across builds, container recreation and updates. Document backup before migration and never use `docker compose down -v` for routine updates.
- `docker compose up -d --build` fetches/builds the referenced Git revision; **it does not automatically redeploy on GitHub push**. Updates require an explicit rebuild and should preferably change a pinned release tag/commit, with documented rollback.
- For Windows development, allow a local-build override using `build: .`; production Compose remains remote-build. Validate in a clean Linux environment without a checked-out repository. Document exact commands, health, login, persistent data and Queue/Reservation deadline smoke tests.
- Internal HTTP can support the in-app notification feed, but browser desktop notifications may be blocked without HTTPS; do not mark browser desktop notification acceptance as passing over insecure HTTP.

## DEP-004 — Public GitHub source repository (CONFIRMED)

- GitHub repository visibility: **Public**. Linux production uses GitHub remote Git build context over HTTPS; no GitHub personal access token is required to fetch a public repository. Do not embed credentials in build URLs.
- **Public source does NOT mean public runtime data.** The SQLite DB contains user emails, local accounts, password hashes, Lab/SUT inventory, BMC and Host IPs, reservations and usage history. Keep the database in a production-only Docker named volume, never in Git.
- Never commit `.env`, actual bootstrap credentials, API keys, secrets, SQL dumps, SQLite database files (`*.db`, `*.sqlite*`), backups, exports, production logs, customer/internal IP inventory or user contact lists. `.env.example` must contain safe placeholders only.
- Commit an explicit `.gitignore`, `.dockerignore`, and `.env.example`. Exclude the local SQLite database and secrets from the Docker build context. Generate passwords/`SECRET_KEY` locally; do not use known defaults for production.
- Public repo must include only anonymized fake sample/seed data. Examples should use RFC 5737 TEST-NET IPs or documentation placeholders; production BMC/Host IP inventory is entered after deployment via authenticated UI.
- The application remains **LAN-only** and login-protected. No public sign-up; do not expose the service to the Internet merely because source is public. Restrict inbound TCP 5088 to trusted internal clients.
- Compose build context should pin a release tag or immutable commit SHA; avoid tracking `main` in production by default. Credentials are not needed for the public remote source.
- Before changing repo visibility or first public push, review entire Git history for committed secrets or internal data, not just the latest tree. If sensitive data was committed, rotate leaked credentials and clean history before publication.
- Acceptance: remote build of public repo succeeds on Linux without GitHub credentials; named-volume data persists across rebuild; `git ls-files` contains no private runtime data.


## DEP-005 — Persistent Local Database Separation (Confirmed)

- The public GitHub repository contains only application source code, migrations, tests, configuration templates, and non-sensitive sample data.
- Production SQLite database files, SUT BMC/Host IP addresses, user accounts, email addresses, password hashes, queue and reservation records, and usage histories must reside only in a persistent Docker named volume on the Linux server.
- Mount `sut-data:/app/data` and use `sqlite:////app/data/sut.db`. Never bake a live database into the image, and never commit `*.db`, `*.sqlite*`, `.env`, secrets, production backups or real lab seed data.
- `docker compose up -d --build` must preserve production data across rebuilds/restarts; warn that `docker compose down -v` deletes the volume.
- Database schema is provisioned/migrated through Alembic. Back up the named volume before potentially destructive migrations and test persistence across container recreation.
- The production server runs Docker Compose against a public GitHub remote build context. Only the Compose file and any private deployment settings are required on the server; source checkout is not required.
- Security note: Keeping the SQLite volume outside GitHub does not protect data from exposed application endpoints, weak credentials, or server compromise. Authentication, authorization, and network controls remain required.

## DEP-006 — Confirmed container HTTP port correction
Host TCP 5088 maps to container TCP 80. Uvicorn binds 0.0.0.0:80; EXPOSE and healthcheck use 80. This supersedes the earlier Day 1/2 container-port-8000 deployment target. Keep UID/GID 10001, no-new-privileges and cap_drop ALL. Compose may use the container-network-namespaced net.ipv4.ip_unprivileged_port_start=80 so the non-root process can bind port 80 without interpreter file capabilities, root startup or host-wide sysctl changes. GitHub Remote Build and named SQLite volume remain required. Verify the published mapping, actual listener, non-root privileges and persistence; company LAN/firewall/two-client checks remain external.


## DEP-007 — Docker Hub image deployment supersedes the primary Remote Build path
Confirmed by Issue #6: release tested Linux amd64 images to `mirage315/sut-reservation-management` on explicit `v*` version tags only. Use scoped GitHub Actions secrets `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`, full-SHA pinned actions and successful automated checks before publishing; record version/source/digest provenance and verify an anonymous published-digest pull. Production administrators use image-only `compose.deploy.yaml` with a version/digest (never default latest), a securely supplied persistent SECRET_KEY, no source checkout/build. Keep 5088:80, non-root UID 10001, all capabilities dropped, no-new-privileges, private-network port-80 sysctl, Alembic startup and named SQLite volume. GitHub Remote Build remains optional for developers. Preserve the existing project/volume when switching deployment files; back up before schema upgrades and do not assume an old image supports a newer database. Do not claim registry publication, a separate-server deployment or LAN acceptance without actual evidence. See docs/deployment.md and docs/dep007-verification.md.
