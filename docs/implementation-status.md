# Implementation status — Issue #4 / Day 3

**Full MVP production acceptance: NOT DONE.** Day 1 PR #1 and Day 2 PR #3 are merged (project owner confirmed). Day 3 started from latest main `719c32e47db148401ffdef2fb87ad11b6c2ac915` on `feat/day3-ui-acceptance`.

## Implemented and verified locally

- Dashboard Card default/Table switch, lab grouping, natural Name/Status sort and shared filters; Card next booking, Table rolling-24h booking projection. Both layouts share Claim/Queue/Reserve/Detail Bootstrap modals, current coordination context, Taipei input, server-side service checks, CSRF, explicit conflict acknowledgement and duplicate-submit protection. Polls preserve modal/filter inputs; success refreshes state without resetting layout/scroll.
- Persistent notification bell, recent-notice preview, complete paginated Inbox, full unread count and recipient-only explicit idempotent mark-read. Read-only 30s polling uses bounded ID windows and deduplicates desktop alerts. Permission is requested only by an explicit click; denied/unsupported/private-IP HTTP retain in-app notices. Desktop bodies omit contacts/purposes; no service worker or closed-site delivery promise.
- Persisted scheduled/start reservation reminders and conflict notices reuse the existing transactional notification helper; existing expiry/offer/no-show/overdue/maintenance notices remain. No deadline, RBAC, history or SQLite concurrency guarantee was removed.
- Responsive calendar/navigation, keyboard/focus handling, authenticated contact display, searchable/filterable/paginated inventory. Fixtures remain fictional two labs/20 SUTs. No production data, secrets or hardware control added.
- Existing Day 1/2 tests retained, with five additional acceptance cases. The interruption test now accounts for the newly committed schedule notice while retaining its strict rollback/exactly-once assertions.

Acceptance map and reproducible commands: [day3-verification.md](day3-verification.md). Previous Day 2 evidence remains in [day2-verification.md](day2-verification.md).

## Observed checks

| Check | Result |
| --- | --- |
| Ruff lint/format, compileall, JavaScript syntax, whitespace checks | PASS |
| Full pytest run | **103 passed** in 84.91 seconds; one non-failing Starlette/httpx TestClient deprecation warning. |
| Baseline Chromium | PASS: login/mandatory password replacement, seed, filters/layout/sort, real 30s polling, stale/retry, profile. |
| Day 2 multi-user Chromium | PASS: FIFO/manual handoff, force release, estimate change, booking edit/cancel/calendar, overlap acknowledgement, check-in priority, history and Detail polling. |
| Day 3 Chromium | PASS: every action/layout combination, 72h custom estimate, duplicate-submit guard, current-state conflict retention, modal polling input safety, Taipei booking, Escape dismissal, mobile detail, Inbox/read and browser Notification API opt-in/denied/unsupported/insecure/dedupe tests. |
| Disposable local Docker Compose | PASS: build/migration/5088/login, non-root, named-volume/session persistence after rebuild/recreate, offline and live deadline checks and restart deduplication. Cold tar backup restored into a different empty volume; sessions/history/notices/schema/ownership/integrity/foreign keys preserved. |
| Published Day 3 pinned GitHub Remote Build | Pending published SHA and run; not yet passed. |
| Hosted GitHub Actions | Not yet observed for Day 3; local checks do not establish hosted CI status. |

The cloud build uses `DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt`. Inherited proxy resolution and approved CA are ephemeral builder settings; TLS/package hashes are verified. Only randomly named synthetic test projects/volumes are removed. Deployment data is never removed.

## Delivery

Day 3 branch push, remote-context verification and PR creation are pending final checks. The actual result will be recorded here; a PR is not claimed in advance.

## Remaining external gates

Actual company Linux host `10.88.26.99`, trusted firewall rules, two independent company LAN clients, production-host backup/restore rehearsal and project-owner sign-off are **unverified** from Codex Cloud. A source-free build on the existing Linux cloud daemon does not prove a clean company OS/network deployment. Hosted CI is reported separately. These gates prevent a full-MVP production-ready declaration even when local application checks pass.
