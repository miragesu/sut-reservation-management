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
| Full pytest run | **103 passed** in 87.40 seconds; one non-failing Starlette/httpx TestClient deprecation warning. |
| Baseline Chromium | PASS: login/mandatory password replacement, seed, filters/layout/sort, real 30s polling, stale/retry, profile. |
| Day 2 multi-user Chromium | PASS: FIFO/manual handoff, force release, estimate change, booking edit/cancel/calendar, overlap acknowledgement, check-in priority, history and Detail polling. |
| Day 3 Chromium | PASS: every action/layout combination, 72h custom estimate, duplicate-submit guard, current-state conflict retention, modal polling input safety, Taipei booking, Escape dismissal, mobile detail, Inbox/read and browser Notification API opt-in/denied/unsupported/insecure/dedupe tests, pending-poll/action refresh collision and granted-but-failed desktop delivery fallback. |
| Disposable local Docker Compose (DEP-006) | **PASS — Host 5088 → Container 80**: build/migration/5088/login, non-root, named-volume/session persistence after rebuild/recreate, offline and live deadline checks and restart deduplication. Cold tar backup restored into a different empty volume; sessions/history/notices/schema/ownership/integrity/foreign keys preserved. |
| Published Day 3 pinned GitHub Remote Build (DEP-006) | **PASS** at final application SHA `eb17c6f7dd4581caff9502e64701de6ab895fc62`: only Compose/settings in the empty working directory; full **5088→80** mapping/listener/health, PID 1 privilege assertions, Chromium login/UI, migrations, persistence, deadlines/restart and independent-volume restore runner passed. |
| Hosted GitHub Actions | **PASS** for final DEP-006 application SHA `eb17c6f`: [run 38736460114](https://github.com/miragesu/sut-reservation-management/actions/runs/38736460114), public conclusion SUCCESS, **4m 51s**. Executes the full pytest, baseline/Day 2/Day 3 Chromium and updated port-80 Docker/backup/restore runner. Earlier `83a22d2` and `d0aa0c7` runs also passed. |

The cloud build uses `DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt`. Inherited proxy resolution and approved CA are ephemeral builder settings; TLS/package hashes are verified. Only randomly named synthetic test projects/volumes are removed. Deployment data is never removed.

## DEP-006: observed Host 5088 → Container 80 result

**Local and public pinned-SHA Remote Build both PASS.** Actual Compose publishing resolves container 80 to 127.0.0.1:5088. Image metadata exposes 80 and defines a working :80 healthcheck; Uvicorn's socket is 0.0.0.0:80 with no :8000 listener. Actual Chromium reaches login/Dashboard/Table/Detail/My Usage through host 5088.

PID 1 is UID 10001, CapEff/CapPrm/CapBnd are zero and NoNewPrivs=1. The container-network namespace has unprivileged-port threshold 80, and an actual non-root bind to port 79 is denied. Compose keeps its private bridge network, all capabilities dropped and no-new-privileges; no host sysctl modification, NET_BIND_SERVICE or interpreter file capabilities are used. SQLite named-volume persistence and a cold restore into another empty volume pass with this mapping. Company LAN acceptance is separate and remains unverified.

The previous `83a22d2`/`d0aa0c7` builds and CI were successful **before DEP-006**, using historical container port 8000. They are not substituted for the new port-80 checks above.

## Delivery

Branch `feat/day3-ui-acceptance` is pushed. Verified application SHA: `eb17c6f7dd4581caff9502e64701de6ab895fc62`. Subsequent delivery commit changes documentation only; the recorded application checks refer to this pinned SHA, not an assumed result for any later documentation-only workflow run. Public pinned-ref Remote Build passed at this application SHA, including backup/restore.

Actual PR creation command:

```bash
gh pr create --repo miragesu/sut-reservation-management --base main \
  --head feat/day3-ui-acceptance \
  --title 'Day 3: Dashboard actions and notification acceptance' \
  --body-file docs/day3-pr.md
```

It failed with **`Post "https://api.github.com/graphql": Forbidden`**. **No PR was created.** Git push and public-page reads work; GitHub API creation is blocked. As allowed by Issue #4, the implementation branch and reviewable [PR body](day3-pr.md) are left pushed for ChatGPT/GitHub to create the PR: https://github.com/miragesu/sut-reservation-management/pull/new/feat/day3-ui-acceptance . No credential values were inspected or copied.

## Remaining external gates

Actual company Linux host `10.88.26.99`, trusted firewall rules, two independent company LAN clients, production-host backup/restore rehearsal and project-owner sign-off are **unverified** from Codex Cloud. A source-free build on the existing Linux cloud daemon does not prove a clean company OS/network deployment. Hosted CI is reported separately. These gates prevent a full-MVP production-ready declaration even when local application checks pass.
