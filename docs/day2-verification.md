# Issue #2 — Day 2 verification

Base: latest `main` at `489b18f` (Day 1 PR #1 merged). Branch: `feat/day2-coordination`.
Scope: https://github.com/miragesu/sut-reservation-management/issues/2 — “Day 2 — Claim, Queue, Reservation & usage history implementation”. The complete issue was read from the public GitHub issue page's embedded data after the GitHub API returned Forbidden.

## Acceptance map

| Issue #2 criterion | Implementation and evidence |
| --- | --- |
| Claim/manual Release/admin force-release, multi-SUT use, uncapped/overflow-safe positive finite estimates | Shared coordination services + API/HTML forms; per-SUT uniqueness, `BEGIN IMMEDIATE`, stable usage identity, admin reason. `test_coordination.py`, `test_coordination_edges.py`, Chromium multi-user workflow. |
| Expected end adjustment and explicit reservation overlap acknowledgement; overdue advisory | Stable usage key, current owner/admin checks, start/now validation, structured 409 conflict details and explicit HTML confirmation; no silent truncation. Worker persists one overdue notice per estimate; no auto-release. Tested in API, HTML, races and real browser. |
| Complete permanent Usage History; archive/deactivation retention | Release writes actual interval/minutes, purpose, actor/reason once; stale key cannot affect a replacement usage. Authenticated filtered/paginated read API + HTML; profile/archive/disable/restart preserve links and records. No purge endpoint/job or cascade deletion. |
| FIFO join/leave/clear, duplicates, notification-first manual Claim, 15-minute rollover, reservation priority | Stable entry keys, FIFO `created_at,id`, explicit admission rule confirmed in chat, active eligible offer, deadline processing and notices in one transaction. Strictly-before/exact deadline tests, leave/rejoin, disabled heads, maintenance/priority pause/resume and both-admin clear tests. |
| Reservations create/view/edit/cancel; 24-hour and 30-day limits, overlap and no-show/check-in | Aware UTC instants, Taipei forms/Calendar, half-open overlap checks under write lock, at-risk warning rather than denying booking against usage estimates. Owner/admin future-state guards, retained cancellations and audit. Boundary tests include exact inclusive horizon, microseconds beyond, 24h+, timezone overflow, check-in vs no-show and manual Claim races. |
| Atomic conflicting state transitions, inactive users and unavailable SUTs | Transaction starts before auth/state reads, database usage uniqueness and bounded busy timeout. Parallel authenticated clients test double Claim, Release retry, duplicate queue join, queue manual Claim, overlap create/edit, cancellation vs Claim, Claim vs maintenance and deadline workers. Inactive records remain; eligibility cannot deadlock FIFO. |
| Background deadline processor independent of open browser; idempotent effects/restart | FastAPI startup catch-up + periodic thread-backed task; production one worker. Separate engines overlapping sweeps, failed-iteration retry and interruption after flushed state/notice prove rollback/idempotency. Docker proves no-show without HTTP/browser and offline offer/no-show catch-up from the named volume across restart. |
| Service/API tests, integration/browser, migrations, Docker and honest progress | Existing Day 1 regressions retained. Added deterministic coordination/edge/race/runtime/migration tests, multi-user Chromium runner and disposable Docker coordination assertions. Exact command results below. Day 3/LAN/hosted CI remain separate gates. |

## Commands and observed results

Final full-suite result is recorded in `docs/implementation-status.md` after completion. Commands executed from the repository root:

```bash
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
.venv/bin/python -m compileall -q backend/app backend/alembic scripts
.venv/bin/pytest -q
.venv/bin/python scripts/browser_smoke.py
.venv/bin/python scripts/browser_day2.py
DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host \
  SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
  .venv/bin/python scripts/container_smoke.py
```

The build uses the environment's approved CA bundle as a transient BuildKit secret and resolves inherited proxy hostnames. No TLS/checksum verification was disabled. No proxy credentials or CA are baked into the runtime image.

Migration tests use fresh databases and a populated Day 1 schema, preserving ownership, queue state, original timestamps/purpose and existing history through upgrade, downgrade/re-upgrade and `alembic check`. Container startup runs migrations, rejects a deliberately broken database path, and uses UID/GID 10001. Synthetic time shifts exist only in disposable test databases/volumes; no production debug API was added.

## Boundary and recovery contract

- Queue and reservation eligibility is checked against the server instant sampled after SQLite's write reservation is acquired. An on-time transition requires `now < deadline`; at the exact deadline expiry/no-show wins. Tests use both `deadline−1μs` and `deadline` with simultaneous worker/client attempts.
- Reservation starts at `now+30 days` and lengths of exactly 24h are accepted; either limit exceeded by one microsecond is rejected. End may fall beyond the 30-day start horizon. Native HTML uses Taipei local time and is subject to identical service checks.
- Fractional positive Claim minutes are supported so a valid sub-minute booking can be manually Claimed; below-microsecond durations are rejected as unrepresentable. Queue requested minutes remain positive integers as specified by its schema.
- A check-in while occupied preserves priority until booked end and never creates a second usage. Once the prior holder Releases, the booked user is notified and must manually Claim. A reservation-specific Release completes that reservation and preserves the original booking row.
- Offers preserve remaining eligible response time while maintenance/usage/reservation protection pauses them. An already-due offer is not revived when maintenance starts. Current reservation wall-clock deadlines still progress. Returning to normal rechecks eligibility and never skips a checked-in reservation.
- Disabled accounts retain usage/queue/reservation records. Disabled entries/owners do not block allocation. Reactivation honors a valid already-issued offer before reusing the earlier retained FIFO position.
- Failed requests roll back their own transaction; the independent background worker still processes due transitions. Mid-transaction simulated failure rolls back state, audit and notification together. A restart cannot duplicate already committed effects.

## Remaining external/full-MVP gates

Actual internal Linux server, firewall/two LAN clients, backup/restore rehearsal and hosted GitHub Actions are unverified from this task. Public source does not authorize a public runtime deployment. Keep named-volume production data and secrets outside Git.

Day 3 remains: Dashboard quick-action modals, complete notification bell/desktop opt-in behavior, broader UI/accessibility acceptance and final full-MVP sign-off. In-app recipient notices, SUT Detail polling, Calendar and History are implemented for the Day 2 workflow; the entire MVP is not declared complete.

PR creation is attempted after pushing the branch. If the GitHub API remains forbidden, the exact failure and manual creation link are recorded with the final delivery; a pushed branch is not described as a created PR.
