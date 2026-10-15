# Issue #4 — Day 3 acceptance evidence

Base: merged Day 1/Day 2 `main`, `719c32e47db148401ffdef2fb87ad11b6c2ac915`. Branch: `feat/day3-ui-acceptance`. Scope: https://github.com/miragesu/sut-reservation-management/issues/4.

## Business-rule acceptance map

The following implementation/test references cover each confirmed rule. Final command outcomes and external gates are recorded in `implementation-status.md`; this map does not imply production LAN sign-off.

| Rule | Behavior and evidence |
| --- | --- |
| BR-001 | Temporary use before reservations, explicit overlap acknowledgement and no silent estimate truncation: coordination/edge/race tests; Day 2 browser; Day 3 modal conflict walkthrough. |
| BR-002 | Background 15-minute no-show, no automatic usage, retained booking: coordination/race/runtime tests; Docker offline and live deadline checks. |
| BR-003 | Checked-in occupied booking retains priority, not no-show; separate Release/Claim: coordination/edge/race tests and Day 2 multi-user browser. |
| BR-004 | FIFO offer is notification, not usage; manual Claim: coordination tests and both Day 2/3 browser runners. |
| BR-005 | Exact offer deadline, timeout audit, next eligible member, pause/restart deduplication: edge/race/runtime tests and container runner. |
| BR-006 | Two fictional Taiwan labs/20 SUTs; UTC storage and Taipei forms/calendar: seed/schema/time-boundary tests; all browser runners. |
| BR-007 | Multiple distinct SUTs per user, one active usage per device: coordination tests, distinct modal claims and database uniqueness. |
| BR-008 | Both admins manage both labs; Super Admin alone provisions accounts: auth/inventory/coordination tests, multi-user browser. |
| BR-009 | Archive only, guarded activity, restore and historical retention: inventory/edge/history tests, Dashboard exclusion. |
| BR-010 | Trim/casefold uniqueness per lab including archives, natural names remain manual: inventory concurrency and DB constraint tests. |
| BR-011 | Positive finite uncapped estimates, presets/custom multi-day, overdue retained until explicit Release: coordination tests and Day 3 72-hour modal claim. |
| BR-012 | Reservation duration >0 and ≤24h, no truncation: API/HTML edge tests and modal uses same service. |
| BR-013 | Future start ≤30×24h inclusive: exact UTC/microsecond and Taipei form tests. |
| BR-014 | Owner/admin future booking edit/cancel, immutable owner/SUT, audit: coordination/edge/race tests, Day 2 browser. |
| BR-015 | Owner/admin estimate edits retain usage identity, overlap needs acknowledgement: coordination/race tests and Day 2 browser. |
| BR-016 | No transfer endpoint; Release/history then separate eligible manual Claim: coordination/race and browser handoffs. |
| BR-017 | Maintenance/out-of-service reason, retained activity, block registrations, pause/resume offers: inventory/coordination/edge tests. Dashboard/modal display uses the same projections; server rechecks mutations. |
| BR-018 | Authenticated read-only 30s Dashboard/Detail/Inbox and global notification polling; stale retry retains display; modal input outside replaced fragment: schema/read-only tests and real 31-second browser waits. Success schedules refresh even if a prior poll is pending. |
| BR-019 | Persisted notices, bell/full unread count, recipient-scoped paginated indefinite history, explicit idempotent read; opt-in desktop support/secure-context checks: Day 3 API tests and browser platform tests for granted/denied/unsupported/insecure and deduplication across polls/reload. |
| BR-020 | Bootstrap/admin-issued temporary passwords, mandatory replacement, strong hashes and session gates: auth/CLI tests and all browser setup flows. |
| BR-021 | Disable sessions without deleting activity, impact review, skip inactive queue, final-admin guard: auth/coordination/edge tests. |
| BR-022 | Authenticated minimal contact DTOs; autoescaped HTML, no security fields; generic desktop body contains no contact/purpose text: auth/projection/history tests and Day 3 browser checks. |
| BR-023 | Own allowlisted profile and password changes, safe audit; live contact projections preserve referenced IDs: auth and Day 3 profile-refresh test. |
| BR-024 | Exactly-once actual usage history, indefinite retention through account/archive/profile changes and restart: history/edge tests; Docker persistence and independent-volume restore. |
| BR-025 | Shared Card(default)/Table dataset, lab groups, shared filters/sort, persisted view across polls: schema tests and baseline/Day 3 browsers. |
| BR-026 | One next future booking on Card; all valid overlapping rolling-24h bookings on Table, half-open endpoints: schema boundary/state tests and modal booking walkthrough. |
| BR-027 | Shared accessible Bootstrap modal in both layouts; selected SUT/context, Taipei dates, CSRF, explicit conflict ack, disabled pending submission, retained errors/input, immediate refresh: `test_day3.py`, existing service/race tests, `browser_day3.py` covering every action/layout combination. |
| BR-028 | Name natural/case-insensitive with ID ties; exact five-state rank within lab; archive/overdue/filter parity: schema and Day 3 rank/tie tests plus baseline polling/browser sort checks. |

## Reproducible validation

```bash
.venv/bin/ruff check backend scripts
.venv/bin/ruff format --check backend scripts
.venv/bin/python -m compileall -q backend/app backend/alembic scripts
.venv/bin/pytest -q
.venv/bin/python scripts/browser_smoke.py
.venv/bin/python scripts/browser_day2.py
.venv/bin/python scripts/browser_day3.py
DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host \
  SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
  .venv/bin/python scripts/container_smoke.py
```

The cloud builder needs its inherited proxy resolved and its existing approved CA supplied as an ephemeral BuildKit secret. TLS and pinned dependency hashes remain verified. These options are environment-specific, not embedded credentials or production requirements.

For public source-free Remote Build, add `SUT_SMOKE_REMOTE_REF=<published-full-SHA>` to the container command. The runner copies only Compose and host build settings to a fresh directory. It tests migrations, startup rejection on broken DB, port 5088, login/password gate, non-root UID 10001, persistence after rebuild/recreation, background processing without HTTP, offline catch-up and restart deduplication. Day 3 additionally stops writers, archives the complete disposable data volume, restores into a different empty volume and checks existing session/history/notices, schema, SQLite integrity and foreign keys. Only randomly named smoke volumes are removed.

Observed public Remote Build **PASS** at final application SHA `eb17c6f7dd4581caff9502e64701de6ab895fc62` including DEP-006 **Host 5088 → Container 80**, with only Compose/settings in the temporary directory. It passed the complete deadline/persistence and cold-backup/independent-volume restore workflow.

Hosted Actions also **PASS** for this final DEP-006 application SHA: [run 38736460114](https://github.com/miragesu/sut-reservation-management/actions/runs/38736460114), conclusion SUCCESS, duration 4m 51s. This independently runs the full pytest/browser/updated container suite on GitHub infrastructure.

The bootstrap JavaScript bundle is vendored from Bootstrap 5.3.8 with the npm package's SHA-512 integrity verified, under the existing MIT license. No CDN, inline JavaScript, relaxed CSP, service worker, email/Teams or device-control integration is added.

## Verification corrections

An initial browser assertion selected action buttons as well as SUT containers because they shared `data-sut-id`; action identity now uses `data-quick-sut`, preserving existing DOM/test contracts. Bootstrap transition timing also exposed early Escape dismissal; the modal now opens without animation, restores focus explicitly and is verified with keyboard dismissal. A rank-test fixture initially omitted the required maintenance reason; the fixture was corrected without relaxing the database constraint.

Adding persisted schedule notifications changed the rollback test's starting count. It now snapshots the count before the simulated interruption, still proving zero committed effects from failure and exactly one additional no-show notice after repeated retry. The transaction guarantee and original assertions about state/audit remain intact.

## DEP-006 port correction

The updated Issue #4 was reread during the same branch. The current deployment contract is **Host TCP 5088 → Container TCP 80**; earlier Day 1/2 and initial Day 3 build evidence used container 8000 and is historical, not proof of DEP-006.

`Dockerfile` EXPOSE/healthcheck, entrypoint, Compose and deployment specifications now agree on port 80. Runtime stays UID/GID 10001, cap_drop ALL and no-new-privileges. Compose sets `net.ipv4.ip_unprivileged_port_start=80` only in the private container network namespace. No root app startup, NET_BIND_SERVICE, interpreter file capabilities or host sysctl change is used.

Image metadata inspection verifies EXPOSE 80 and the real image healthcheck command is executed successfully. The container runner asserts actual `docker compose port ... 80` returns 127.0.0.1:5088, PID 1 UID 10001, CapEff/CapPrm/CapBnd zero, NoNewPrivs=1, namespace threshold 80, listening socket 0.0.0.0:80, internal /health:80, no old :8000 listener and denied port-79 binding. Chromium then signs in and opens Dashboard/Table/Detail/My Usage through host 5088. Persistence, background deadlines and independent-volume restore are rerun with the new mapping. Local and published-SHA Remote Build **PASS** for all of these assertions, including actual Chromium over 5088→80. Final outcomes and published SHA are recorded in implementation-status.md.

DEP-006 does not require a schema change. Updating from older images requires the matching Compose revision as well as the new pinned image source SHA; pre-DEP-006 rollback must also restore its historical port mapping. No data-volume deletion is needed.

Final browser cases also cover a successful action racing an outstanding notification poll and a granted Notification permission whose constructor throws. The former queues an immediate follow-up read; the latter leaves an explicit Inbox fallback cue.

## External gates

The actual company host `10.88.26.99`, firewall allowlist, two independent LAN clients, production-host backup/restore and owner acceptance are not exercised from Codex Cloud. A Linux cloud Docker daemon and empty remote-build working directory do not prove a fresh company OS/network deployment. Hosted GitHub Actions must be reported separately from local checks. Full MVP production acceptance remains **NOT DONE** until these gates pass.
