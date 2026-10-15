# Day 1–2 domain and transition map

All timestamps cross application boundaries as aware UTC and are persisted as UTC in SQLite; HTML uses Asia/Taipei. Foreign keys restrict deletion, with no ORM delete cascades. A write unit of work obtains SQLite BEGIN IMMEDIATE before authorization and conflict reads. Busy timeout is five seconds; contention returns 503 with Retry-After instead of bypassing checks. Run one Uvicorn worker.

| Domain | States / transitions | Owner of changes |
| --- | --- | --- |
| Account | admin-issued temporary credential → mandatory password change → active; active ↔ disabled | Super Admin creates/resets/changes role/status; owner changes own profile/password. CLI bootstrap only while no Super Admin exists. Last active Super Admin cannot be demoted/disabled. |
| Session | random token (only SHA-256 stored) → expiry/revocation | Login rotates; logout removes; password reset/change or deactivation revokes every session. Signed HttpOnly SameSite=Lax cookie; CSRF required for all mutations, including login. |
| Lab | create → edit → delete only if no SUTs, including archived | Either admin across all labs |
| SUT lifecycle | active → archived (only without current usage, queue, valid current/future reservation) → restored | Either admin, audited; names reserved in each lab after trim/casefold, including archives; lab immutable |
| Operational condition | normal ↔ maintenance/out_of_service; reason required while unavailable | Either admin, audit and acknowledge existing activity; no usage/queue/reservation removal; existing affected users get persisted notices |
| Current usage | absent → manually claimed → released to one history record | Coordination service; one active row per SUT, no unique user restriction; no auto-release |
| Queue | waiting → notified → manual Claim/removal; leave/expiry audited before removal | Coordination service/worker; FIFO created_at,id; positive duration; unique active SUT/user; no persisted position |
| Reservation | confirmed → checked-in waiting_for_release or claimed → completed; confirmed → no_show/cancelled | Coordination service/worker; retained records, half-open nonoverlap checked under serialized writes; no implicit usage creation |
| History | append once per released usage identity, retained indefinitely | Release service; unique usage_key; never purged |
| Notification | unread → read | Recipient-scoped API and Inbox; unique event_key per recipient makes retries idempotent |
| Audit | append only, IDs/time/safe metadata | Mutating services; no passwords/tokens/hashes |

Effective state is derived: operational Maintenance/Out of Service takes presentation priority, retaining In Use/overdue as secondary context; otherwise current usage → In Use, active reservation covering now → Reserved, else Available. Archive is a lifecycle flag, not an effective status. No hardware actions exist.

Day 2 supplies coordination services, API/HTML actions, read-only History/Calendar/My Usage/Inbox and a lifespan-managed deadline processor. Every mutation and sweep obtains the SQLite write reservation before sampling server UTC time and checking state. Startup catch-up precedes traffic; repeated/overlapping sweeps atomically deduplicate effects. GET/polling never reconciles state. See `day2-verification.md` for behavior evidence, including concurrent clients and container restart checks.

`current_usages.usage_key` survives into exactly one history row and protects stale Release/estimate requests from touching a replacement usage. Queue `entry_key` protects a rejoined entry from stale Leave requests; generation and event keys distinguish offers even if SQLite reuses an integer row ID. Migration `b12d2c001001` backfills Day 1 live rows and adds complete history metadata.

A live offer pauses with remaining eligible response microseconds during maintenance, recorded usage or reservation protection; already-due offers expire before entering maintenance and cannot be resurrected. Returning to normal resumes only after eligibility is rechecked. Inactive accounts retain queue/reservation records; skipped inactive members cannot block offers, and reactivation cannot steal a currently live offer. Once it resolves, retained FIFO order applies again. Reservation wall-clock deadlines continue while maintenance is active.

Check-in is owner-only and strictly before the 15-minute deadline/booked end. Attendance is retained as `waiting_for_release` whether the SUT is occupied or free; it never implicitly creates usage or becomes no-show while awaiting Release. The owner separately Claims within the remaining booking. At booked end it completes, even if a prior holder remains overdue. Releasing a reservation-specific usage completes that booking early and releases its remaining protection; timestamps and history remain. No automatic usage Release exists.

Day 3 adds shared Dashboard action modals, recipient-scoped notification history/unread projections, browser opt-in/fallback and verified UI workflows. Notification GETs remain read-only; schedule/start reminders use the same transactional deduplicated service. Production LAN/owner acceptance remains separate; see day3-verification.md. There are no placeholder coordination routes.
