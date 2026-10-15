# Day 1 domain and transition map

All timestamps cross application boundaries as aware UTC and are persisted as UTC in SQLite; HTML uses Asia/Taipei. Foreign keys restrict deletion, with no ORM delete cascades. A write unit of work obtains SQLite BEGIN IMMEDIATE before authorization and conflict reads. Busy timeout is five seconds; contention returns 503 with Retry-After instead of bypassing checks. Run one Uvicorn worker.

| Domain | States / transitions | Owner of changes |
| --- | --- | --- |
| Account | admin-issued temporary credential → mandatory password change → active; active ↔ disabled | Super Admin creates/resets/changes role/status; owner changes own profile/password. CLI bootstrap only while no Super Admin exists. Last active Super Admin cannot be demoted/disabled. |
| Session | random token (only SHA-256 stored) → expiry/revocation | Login rotates; logout removes; password reset/change or deactivation revokes every session. Signed HttpOnly SameSite=Lax cookie; CSRF required for all mutations, including login. |
| Lab | create → edit → delete only if no SUTs, including archived | Either admin across all labs |
| SUT lifecycle | active → archived (only without current usage, queue, valid current/future reservation) → restored | Either admin, audited; names reserved in each lab after trim/casefold, including archives; lab immutable |
| Operational condition | normal ↔ maintenance/out_of_service; reason required while unavailable | Either admin, audit and acknowledge existing activity; no usage/queue/reservation removal; existing affected users get persisted notices |
| Current usage | absent → manually claimed → released to one history record | Day 2 service; one active row per SUT, no unique user restriction; no auto-release |
| Queue | waiting → notified → manual Claim/removal; leave/expiry audited before removal | Day 2 service/worker; FIFO created_at,id; positive duration; unique active SUT/user; no persisted position |
| Reservation | confirmed → checked-in waiting_for_release or claimed → completed; confirmed → no_show/cancelled | Day 2 service/worker; retained records, half-open nonoverlap checked under serialized writes; no implicit usage creation |
| History | append once per released usage identity, retained indefinitely | Day 2 release service; unique usage_key; never purged |
| Notification | unread → read | Recipient only (API/UI Day 3); unique event_key per recipient makes retries idempotent |
| Audit | append only, IDs/time/safe metadata | Mutating services; no passwords/tokens/hashes |

Effective state is derived: operational Maintenance/Out of Service takes presentation priority, retaining In Use/overdue as secondary context; otherwise current usage → In Use, active reservation covering now → Reserved, else Available. Archive is a lifecycle flag, not an effective status. No hardware actions exist.

Day 1 supplies the complete schema and inventory/auth transitions. Day 2 must implement coordination transitions, runtime eligibility checks, reservation duration/horizon validation, single deadline processor, maintenance queue pause/resume and inactive-user FIFO eligibility. Those behaviors are not established by the schema alone. Day 3 adds full dashboard actions, notification UI and browser acceptance. No stub coordination endpoints are exposed in Day 1.
