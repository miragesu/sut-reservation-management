# Confirmed SUT Business Decisions

## BR-001 — Borrowing before reservation (Confirmed)

A queued user (FIFO head) may temporarily use a SUT until the next confirmed booking starts. If the requested duration extends past that start, show a prominent warning with the next reservation time and holder and recommend an expected end time no later than booking start. Do not silently shorten the user's entered expected duration; if they choose a later expected end, require explicit acknowledgement and display a scheduling-conflict warning. Do not force-release at the boundary. Other booking conflicts still prevent claims during protected windows.

## BR-002 — No-show grace period (Confirmed)

Reservation owner must manually Claim. Allow 15 minutes from the reservation start; if not claimed by that deadline, mark the reservation `no_show`, retain the row, and remove the remaining reservation block. Process through a background job independent of page visits, with an atomic, idempotent state transition and retry-safe boot behavior. If the SUT has no active holder, attempt FIFO queue promotion. Never force-release a current holder or create overlapping active usages.

## BR-003 — Checked-in reservation while SUT still in use (Confirmed, advisory)

Choose option B, interpreted as a status/notification workflow only. If the reserved user checks in within the 15-minute BR-002 window while the previous user is still recorded as active, record `waiting_for_release` and `checked_in_at`, mark them as present (not no-show), prominently notify the current user and admin, and indicate the reservation has handoff priority. On the previous user's *recorded* release, notify the checked-in user that they may Claim; do not create usage automatically. Keep reservation handoff priority ahead of FIFO until its end, cancellation, or a future separately-approved abandonment policy. A checked-in reservation is never marked no-show simply because the prior user is late releasing. This system does not block SSH/BMC/network access or forcibly disconnect users. No device-level enforcement in MVP.

## Product boundary — coordination, not control (Confirmed)

Claims, reservations, and queue transitions reflect self-reported status, reminders, and scheduling priority. They never assert control over physical access. Warnings are in-app for MVP; Teams/push remains future scope. Duplicate active records are prevented for data consistency only.

## BR-004 — FIFO handoff: notification first, manual Claim (Confirmed)

When an active SUT usage is released, notify the FIFO queue head that it is their turn using an in-app notification/status indicator. Preserve their queue entry as `notified` until they manually Claim or voluntarily leave the queue. Notification is **not** a claim: do not create `current_usages`, do not start the usage timer, and do not display the queued user as `In Use` before Claim. The queue head's Claim creates the active usage and removes their entry in one transaction. Existing checked-in reservation priority is respected. No SUT SSH/BMC/hardware access controls are involved.

## BR-005 — 15-minute queue offer response deadline (Confirmed)

When a user at the FIFO head is notified that the SUT is ready for them, start a **15-minute** offer window at `notified_at` (UTC). Only a successful *manual* Claim during that window starts usage. At or after the deadline, if they have not claimed, atomically mark the offer `expired`, remove the entry from the **active** queue, preserve an audit event (user, SUT, timestamps, reason `offer_timeout`), and notify both the timed-out user and the next FIFO waiting user. If eligible, notify the next person and set their own `notified_at` / 15-minute deadline; if a reservation is protected, wait rather than notify a new queue user. No equipment access is disabled. The user who timed out may join the back of the queue again, not reclaim the old position.

A periodic, retry-safe worker processes deadlines independently of page visits and on restart; Claim and expiry must be race-safe under a single transaction and recheck current time and reservation priority. If a user leaves the queue while notified, advance immediately under the same eligibility rules. Queue offer expiration must **not** end an active usage or modify a reservation. In-app notifications are sufficient for MVP.

## BR-006 — Taiwan-only labs and time display (Confirmed)

MVP serves **two laboratories in Taiwan with approximately 20 SUTs total**, rather than Taiwan/US multi-region operations. All scheduling UI and inputs use `Asia/Taipei` (UTC+08:00), clearly labeled. Store and compare timestamps as UTC. Do not implement US-lab timezones, per-user timezone selection, or multi-region infrastructure in MVP. This simplifies display only; reservation and queue deadlines still use reliable server-side time.

## BR-007 — Multiple SUT Claims by One User (Confirmed)

A user may hold active usage records for multiple **different SUTs** concurrently (e.g., Kevin using TW-SUT-01 and TW-SUT-02). No per-user maximum is enforced in the MVP. Each SUT has its own Claim time, expected end time, Release, overdue indicator, and usage history; releasing one SUT must not change another. Keep at most one active usage record **per SUT** to preserve record consistency. This system coordinates self-reported status only and never enforces real hardware access.

## BR-008 — Lab Admin Global Scope (Confirmed)

All Lab Admin users can manage **both** Taiwan labs and their SUTs; no assignment per lab. They can create/update/delete labs and SUTs subject to deletion/audit guards, force-release a **recorded** current usage, and clear queues for either lab. User/account and role management and system-wide configuration remain **Super Admin only**. Standard Users cannot perform administrator mutations. No `lab_admin_assignments` table, assigned-lab RBAC check, or physical device access control in MVP. Test cross-lab administration and denial for standard users.

## BR-009 — SUT archival and history retention (Confirmed)

All Lab Admins and Super Admins use an **Archive** action in place of permanent SUT deletion. This is a soft delete for **all** SUTs regardless of previous history: `is_archived`, `archived_at`, and `archived_by_user_id` are persisted. Archived SUTs disappear from ordinary dashboard, KPI totals and active inventory and are not eligible for Claim, Queue, or Reservation; admins can include archives in inventory and restore them. All historical usage, reservations and audit records keep their SUT references. MVP exposes **no hard-delete SUT endpoint**.

Archiving is refused with `409 Conflict` when an active usage, active queue/offer, or active future/ongoing reservation exists. The user must first coordinate Release, queue clearing, or cancellation normally; archiving does not auto-cancel these. Archive and restore are authorized server-side and audited. Restore does not revive old bookings/usages/offers. This is a record-management behavior, not physical SUT access control.

## BR-010 — SUT names scoped to Lab (Confirmed)

Lab Admin or Super Admin manually assigns a name when registering a SUT. A name is unique within one Lab; different Labs may use the same name. Validation trims leading/trailing whitespace and treats case-only differences as duplicate. The DB enforces uniqueness using `(lab_id, normalized_name)` or equivalent, not application validation alone. Archived SUT names remain reserved to protect historical references and simplify restoration. Renaming applies the same checks; SUT Lab assignment is fixed in MVP.

## BR-011 — Uncapped expected usage duration, reminder-only overdue (Confirmed)

A user may Claim a SUT for an expected duration of 1/2/4/8 hours or any **positive custom duration**; there is no business-imposed upper bound on the expected usage length. The form must allow multi-day estimates, while API input validation rejects invalid or unrepresentable values. `expected_end_time` is informational. At the expected end time, keep the recorded active usage and mark it `Overdue` until the owner releases it or an authorized admin force-releases the *record*. Display reminders and potential reservation conflicts in-app; do not auto-release, disconnect users, or control SUT hardware. Store actual duration using the real release timestamp in usage history. This rule is about **Claim usage duration only**; the reservation duration is confirmed separately in BR-012; advance booking horizon is confirmed in BR-013.

## BR-012 — Reservation maximum duration: 24 hours (Confirmed)

A single reservation has a strictly positive elapsed duration of **at most 24 hours (1,440 minutes)**. Exactly 24 hours is valid; anything longer is invalid. Validate server-side for API and HTML; return an actionable error instead of silently trimming. The limit applies separately to each reservation, **not** to BR-011 Claim estimated usage duration. Existing reservation overlap protections continue to apply. The maximum advance booking horizon is confirmed under BR-013. All UI input/display is Asia/Taipei, and comparisons use normalized UTC instants.


## BR-013 — Reservation advance booking horizon: 30 days (Confirmed)

Users may create reservations with a start time strictly later than the server's current time and no later than **30 × 24 hours (720 hours)** after submission, including the exact boundary. This constraint applies to the reservation **start** time, not its end: an eligible start may have an end after the horizon, provided BR-012's elapsed reservation duration is greater than zero and at most 24 hours. Validate both API requests and HTML forms using timezone-aware UTC instants based on server time; show and enter times in Asia/Taipei. Return a clear validation error for past starts or starts beyond the 30-day limit; do not silently move dates. Test just-before/at/just-after horizon, past times, and day-boundary conversions. No hardware access restriction is implied.


## BR-014 — Edit and cancel upcoming reservations (Confirmed)

A user can edit or cancel their **own** reservation only while its start time is still in the future and status is `confirmed`. All Lab Admins (for both Taiwan labs) and Super Admins can edit/cancel any such upcoming reservation. Editing changes start/end time and purpose, but does not transfer the reservation to another SUT or user in MVP. The edit must be validated as a new booking against BR-012 (positive and at most 24h), BR-013 (future start and at most 30 days ahead from edit submission), and no overlapping active reservation on the same SUT (excluding the reservation being edited). Updates must be atomic and audited with before/after values. Cancellation is a recorded state change, never hard deletion. Neither action is allowed after the reservation begins or has been claimed/checked in/completed/no-show/cancelled. Display actionable authorization/state/conflict errors. On cancellation, update scheduling indicators and eligible Queue notification flows; never manipulate physical SUT access.

## BR-015 — Extend expected SUT usage time (Confirmed; Option B)

The current SUT usage owner can directly extend `expected_end_time` without releasing and claiming again; admins can adjust the recorded expectation as needed. No business-imposed maximum duration applies (BR-011). Where extension would overlap another user's reservation, the system must display the reservation details and require explicit acknowledgement before storing the new estimate, but must not block the adjustment after acknowledgement. The reservation remains intact and the conflict is visible for coordination. Audit old/new estimates, actor, time, and acknowledgement. No automatic release, physical handover, or SUT access restriction is implied.

## BR-016 — Usage handover via Release then Claim (Confirmed; Option A)

No direct user-to-user SUT handover action is included in MVP. The current holder explicitly Releases; the next eligible user separately and manually Claims. Release triggers existing checked-in reservation priority and FIFO queue notifications (BR-003/004/005); it must not silently assign ownership or allow bypassing queue/reservation order. Keep both actions and actual usage intervals separately auditable. The system does not control hardware access.


## BR-017 — SUT maintenance/fault condition — CONFIRMED (Option B)
- Lab Admin/Super Admin may mark SUT `Maintenance` or `Out of Service`, requiring a reason; may return it to `normal`.
- Both conditions are prominently displayed in status UI, and **new application Claim/Queue/Reservation registrations** are suspended; existing activity/history is preserved and exposed with warnings, not silently ended.
- No device lockout, SSH/BMC cut-off or forced release. Queue offers must pause/resume without unfair skipping, while respecting reservation priority.
- Verify roles, audit, warnings and race-safe behaviour through tests.


## BR-018 — SUT status and notification refresh (Confirmed: Option B)

For the Taiwan-only MVP (~20 SUTs), Dashboard, SUT Detail, and the in-app notification area automatically update every **30 seconds** with read-only authenticated HTTP polling. Changes following a user's own successful actions should appear immediately. Show last refresh/stale data on errors, retry without deleting existing display data, preserve unsaved edits, and avoid duplicate notification banners. All state changes and deadline expirations happen on server-side mutation endpoints/jobs, never via polling GET. No WebSocket/SSE or physical SUT access control in MVP.


## BR-020 — Admin-provisioned local accounts & mandatory first-login password change (Confirmed)

Option B. Only Super Admin creates user accounts and assigns roles; no self-registration or pending-approval feature in MVP. The administrator sets a temporary password and shares it securely outside the application. Users must replace it at first login before accessing normal protected pages or APIs; passwords are salted/hashed and never returned after creation or written to audit logs. Super Admin may reset a temporary password, again requiring change. The initial Super Admin is provisioned through a secure one-time CLI, not a public route. Email and Teams are not required to onboard users.


## BR-019 — Notification channels: in-app + browser desktop (Confirmed; Option B)

The MVP provides persistent, user-specific in-app notifications and optional browser desktop alerts when the user explicitly enables browser permission. Dashboard/SUT Detail notification information refreshes every 30 seconds per BR-018. Desktop alerts are best-effort while the site is open and the browser/OS allows them; **no delivery after the website is closed is guaranteed**. Use read/unread state and deduplication, and do not trigger permission requests without a user gesture. Email and Microsoft Teams integrations are explicitly deferred to future enhancements. This is a coordination and notification tool, not hardware access control.

## BR-021 — Disabled user account and outstanding Lab resources (Confirmed; Option B)
Super Admin disables login, preserves all existing current-usage, queue and future-reservation records, and receives an explicit review list of the affected resources. No automatic Release, Queue removal, Reservation cancellation or SUT access change. Disabled sessions stop working. Admins take permitted manual actions with audit; inactive queue entries cannot block progress and remain traceable. Reactivation is possible.


## BR-022 — Contact information visibility (Confirmed; Option C)
All authenticated RD users may see colleagues’ display name, team, work email, current usage/queue/reservation times, and recorded usage/reservation purpose on relevant SUT pages. Work emails assist internal coordination only; no anonymous access, passwords or security metadata. Add `users.team`, distinguish SUT owner team, and allow optional claim purpose. Admin account deactivation does not erase historical attribution.

## BR-023 — User-managed profile (Confirmed: Option B)
Authenticated active RD users may update only their own display name, team, work email and password. Username, role, permissions, account activation and security flags remain Super Admin-controlled. Enforce work-email validity/uniqueness, verify current password for voluntary password changes, protect sessions and forms, respect mandatory first-login password changes (BR-020), and audit without storing secrets. Updated contact details appear on authenticated coordination pages; historical usage references remain tied to the same user ID.


## BR-024 — Usage History retention (Confirmed: Option A)
Usage History is retained indefinitely, without automatic time-based deletion. History records remain attributable and queryable when SUTs are archived or accounts deactivated, and after user profile edits. No usage-history purge endpoint or background expiry task is included in MVP. Release writes actual start/end/duration and is idempotent. Regular database backups are recommended separately; this retention policy does not guarantee recovery from storage failure.

## Day 2 Queue admission clarification — confirmed 2026-10-15
When a SUT is Available and has no queue entries, users must directly Claim; joining Queue is allowed only when In Use, Reserved, or when a queue already exists. The user explicitly confirmed the recommended SPEC rule while implementing Issue #2. Queue requests supply a positive requested duration; the API does not silently invent a requested duration.


## DEP-006 — Host 5088 → container 80 (confirmed 2026-10-15)
The project owner updated Issue #4 during Day 3: Compose publishes 5088:80, Uvicorn binds 0.0.0.0:80, and Dockerfile/entrypoint/healthcheck/docs/tests must agree. Non-root runtime is mandatory; preserve GitHub Remote Build and SQLite named volume. The implementation uses a private-container-network sysctl (unprivileged port start 80), retains cap_drop ALL and no-new-privileges, and does not modify the host sysctl or grant the Python interpreter file capabilities. Actual company LAN acceptance remains unverified without host access.


## DEP-007 — Confirmed Docker Hub release/operator path (2026-10-15)
Issue #6 changes the primary operator workflow to one image-only Compose file plus host-managed secrets, pulling public versioned/digest-pinned images from mirage315/sut-reservation-management. Explicit version tags trigger tested publishing; ordinary main pushes do not. GitHub Remote Build remains an optional developer path. DEP-006 port/privilege and persistent-volume requirements remain. Registry publishing credentials belong only in GitHub Actions secrets, never source or production server settings. Real publishing/pull and company LAN checks remain independent acceptance gates.


## DEP-008 — Administrator deployment / bind storage (confirmed)
The project owner's DEP-008 request supersedes Named Volume requirements **only for the primary image-only production deployment**. `compose.deploy.yaml` uses long-form bind `/data/sut-reservation-data` → `/app/data`, with `create_host_path: false`; operators verify the persistent `/data` mount and prepare UID/GID 10001 ownership/mode 700. Existing Named Volumes must not be deleted or migrated automatically. The optional Remote Build path and disposable recovery test volumes remain Named Volumes. Preserve the published v1.0.0 image, application code, 5088:80, non-root/security/deadline/migration behavior. See docs/deployment.md for reviewed Compose selection, secure local configuration, cold backup/empty-directory restore, upgrade and manual migration. Actual production/LAN validation remains external.
