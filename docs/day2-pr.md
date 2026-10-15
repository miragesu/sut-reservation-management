Closes #2.

## Scope and behavior

Add the Day 2 coordination workflows on merged Day 1 `main`: manual Claim/Release, audited admin force-release, multi-SUT use and uncapped positive estimates, FIFO notification followed by manual Claim, reservations/check-in/no-show, and durable Usage History. Shared transaction services back typed JSON APIs and browser forms, Calendar, My Usage and Inbox.

All contested operations acquire SQLite `BEGIN IMMEDIATE` before reading/rechecking state. Stable usage/queue identities protect newer records from stale retries. Claims/estimate changes require explicit acknowledgement for another user's booking overlap; estimates are never silently shortened and overdue use is never automatically released. Checked-in reservation holders retain priority until booked end, then separately Claim after manual Release. Maintenance preserves activity and pauses remaining offer time; inactive members retain records without deadlocking FIFO.

The FastAPI lifespan catches up deadlines before serving and runs the processor independently of HTTP/browser activity. State, audit and recipient/event-deduplicated notices commit atomically; failures roll back and retry. Production remains one worker with SQLite in the existing named volume. No hardware access actions, production data or secrets are introduced.

## Migration and API

Alembic `b12d2c001001` backfills stable identities for existing Day 1 live usages/queues, adds resumable offer fields and history purpose/release actor/reason metadata. Upgrade/backfill/downgrade/re-upgrade and integrity checks preserve existing Day 1 data. Back up before production migration.

Adds Claim/Release/force-release/expected-end, Queue join/leave/clear, reservation create/view/edit/cancel/check-in, History/My Usage, coordination and recipient notification APIs. `usage_key` is required for release/estimate changes; `entry_key` is required for leaving Queue. See authenticated OpenAPI and README for payloads. Browser times use Asia/Taipei; JSON boundaries use aware UTC. Fractional positive Claim minutes fit short bookings; Queue requested duration remains a positive integer.

## Validation

- Ruff lint/format and compileall pass.
- `pytest -q`: **98 passed**, including retained Day 1 tests, microsecond deadline/booking boundaries, permissions, conflict acknowledgement, real parallel HTTP clients, stable-key retries, populated migration backfill, interrupted-transaction rollback, overlapping processors and restart recovery.
- Chromium baseline and multi-user Day 2 flows pass, including actual 30-second Detail polling retaining unsaved input.
- Docker smoke passes migration-before-startup, rejected broken migration, :5088 health/login, UID 10001, named-volume down/rebuild/recreate persistence, real no-browser background expiry and restart-idempotent notifications.
- Public pinned-ref Remote Build/source-free Compose smoke also passes at application commit `344d305cdc0945a1d76ca95b393fd77d5d53b596`, including the complete Day 2 deadline/restart assertions.
- Full acceptance mapping and exact commands: `docs/day2-verification.md` and `docs/implementation-status.md`.

## Manual QA

1. Migrate an isolated database and bootstrap/provision synthetic users; complete mandatory first-password change.
2. Claim two different SUTs as one user, enqueue two colleagues on one, then Release. Confirm only the notified eligible member can manually Claim and no usage is created by notification.
3. Create/edit/cancel a future reservation; reject >24h, >30-day start and overlap. Try a Claim/estimate crossing a booking and confirm explicit acknowledgement preserves the entered estimate.
4. Check in while another user holds the SUT; Release, verify reservation priority over FIFO, then manually Claim. Inspect recorded History and recipient notices.
5. Exercise maintenance pause/resume and account deactivation with outstanding-resource review; retain records and allow authorized explicit cleanup.
6. Run the disposable browser/container runners, including deadline catch-up and repeated restart assertions.

## Remaining gates

Day 3 Dashboard action modals, notification bell/desktop opt-in and final full-MVP UI acceptance remain unimplemented. Actual internal host/firewall/two LAN clients, production backup/restore rehearsal and hosted CI are unverified; local passing checks do not establish those outcomes. The full MVP is **NOT DONE**.
