# Implementation Status

2026-10-15 (Asia/Taipei). **Day 2 code/behavior acceptance checks PASS; implementation branch pushed; PR creation blocked by GitHub API. Full MVP NOT DONE.** Day 3, hosted CI and real production/LAN acceptance remain separate gates.

## Baseline and scope

Day 1 PR #1 was merged into `main`; this work starts at `489b18f` on `feat/day2-coordination`, without overwriting the baseline. Issue #2 was read in full via its public GitHub page after API access failed. Confirmed specifications, decisions and the domain map were read. The user explicitly confirmed that an Available SUT with no queue must be Claimed directly; Queue admission requires In Use, Reserved, or an existing queue. The confirmation is recorded in `docs/decisions.md` and SPEC.

Day 1 authentication/RBAC/inventory/archival and Docker persistence behavior remains implemented and regression-tested. The former Day 1 API blocker did not prevent the user subsequently creating and merging PR #1; that historical blocker is not a claim that PR #1 remains unmerged.

## Delivered Day 2 behavior

- Shared serialized coordination services for manual Claim/Release/admin force-release, one usage per SUT with multiple different SUTs per user, positive finite uncapped estimates and explicit reservation-overlap acknowledgement. Fractional minutes support short valid bookings; below-timestamp-precision/overflow inputs are rejected. Overdue is advisory, with persisted reminders and no automatic Release.
- Stable usage/entry identities prevent stale retries from affecting replacement/rejoined records. Release writes exactly one retained history with actual interval, purpose, actor/reason and reservation attribution. No direct handover or hardware action exists.
- FIFO Queue join/leave/admin clear with duplicate prevention, eligible-member notification followed by manual Claim, exact 15-minute expiry and next eligible offer. Disabled records remain, maintenance/usage/reservation protection pauses remaining offer time, and reactivation cannot steal a live offer.
- Reservation API and HTML create/view/edit/cancel/check-in, UTC/Asia-Taipei boundaries, >0 and ≤24h elapsed duration, strictly future start ≤30 days inclusive, serialized half-open overlap checks and at-risk usage warning. Check-in while occupied preserves priority until booked end; no-show occurs at the deadline only without attendance. Handoff requires manual Release and separate Claim.
- History, Calendar, My Usage, live SUT Detail and recipient-scoped Inbox. Contact projections exclude credentials/security fields; read endpoints never expire state or mark notices read. Calendar retains historical states and shows current SUT maintenance reason/In Use context. Detail polling preserves unsaved forms.
- Startup catch-up plus periodic background deadline task, independent of browsers/HTTP. Transactional state/audit/notice effects are deduplicated across retry, interruption, overlapping processors and restart. Production Compose explicitly enables the processor with one worker, retaining the existing SQLite named volume.
- Migration `b12d2c001001` backfills Day 1 usage/queue keys, preserves ownership/state/original timestamps, and adds offer pause and complete history metadata. No runtime `create_all`, data purge or unsafe cascade is introduced.

Full acceptance mapping: `docs/day2-verification.md`. API payloads, operational semantics and reproducible commands: README and authenticated OpenAPI. Only verified Day 2 facts are checked in TASKS; mixed Day 3 criteria stay unchecked.

## Observed validation

| Command / check | Actual result |
| --- | --- |
| `.venv/bin/ruff check backend scripts` | PASS |
| `.venv/bin/ruff format --check backend scripts` | PASS |
| `.venv/bin/python -m compileall -q backend/app backend/alembic scripts` | PASS |
| `.venv/bin/pytest -q` | **98 passed**, one non-failing Starlette/httpx TestClient deprecation warning. Includes 39 retained Day 1 cases plus coordination, edge, race, runtime and populated migration tests. Latest full run: 70.25 seconds. |
| Maintenance/archive targeted rerun after strengthening Leave Queue assertions | **2 passed**; both Maintenance and Out of Service permit explicit Release/Leave while blocking new registrations. |
| `.venv/bin/python scripts/browser_smoke.py` | PASS: baseline actual Chromium login/mandatory password replacement, layout/filters/sort, real 30s polling, stale/retry, profile. |
| `.venv/bin/python scripts/browser_day2.py` | PASS: three browser sessions exercising FIFO/manual handoff, force-release, estimate edits, booking create/edit/cancel/Calendar, overlap confirmation, checked-in priority, History/Inbox and real 30s Detail polling preserving inputs. |
| Local disposable Compose smoke | PASS: build, migrations, rejected broken database, :5088 login/health/inventory, UID 10001, integrity/migration check and named-volume data/session retention through down/rebuild/recreate. Day 2 checks prove offline expiry/no-show catch-up, no automatic usage, live no-show without HTTP/browser, and notification idempotency across restart. |

Docker command used:

```bash
DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host \
  SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
  .venv/bin/python scripts/container_smoke.py
```

This environment requires its inherited proxy resolved for the builder and its existing approved CA bundle passed as an ephemeral BuildKit secret. TLS/package-hash verification stays enabled; no proxy credentials or private CA are copied into the runtime image. Synthetic timeline shifts are restricted to the runners' disposable SQLite/Compose project. Test processes and volumes are cleaned up.

Migration tests execute fresh `upgrade head`, `alembic check`, initial down/up, and populated Day 1 → Day 2 → Day 1 → Day 2 backfill checks. Race tests cover simultaneous Claim/Release/Queue/reservation writes, maintenance, exact deadline±1μs Claim/check-in vs workers, independent processor engines and rollback after flushed-but-uncommitted state/notice/audit.

## Delivery

Branch `feat/day2-coordination` is pushed. Application commit: `344d305cdc0945a1d76ca95b393fd77d5d53b596` (subsequent commit records delivery evidence only). PR description: `docs/day2-pr.md`.

Public pinned-ref Remote Build **PASS** at that SHA, including the complete disposable Day 2 Compose workflow from a temporary directory holding only Compose/build settings, without a source checkout. This used the existing cloud Docker daemon. Actual output: `Restart catch-up: one timeout, one no-show, no automatic usage`; `Live deadline processing without HTTP/browser: OK`; `PASS: Day 2 Docker Claim/Release/FIFO/history, offline deadline catch-up, live background no-show and restart-idempotent notifications`; and named-volume/session persistence after down/rebuild/recreate. Reproduce by adding `SUT_SMOKE_REMOTE_REF=344d305cdc0945a1d76ca95b393fd77d5d53b596` to the Docker smoke command above.

An actual creation attempt was made:

```bash
gh pr create --repo miragesu/sut-reservation-management --base main \
  --head feat/day2-coordination \
  --title 'Day 2: coordination workflows and background deadlines' \
  --body-file docs/day2-pr.md
```

It failed with **`Post "https://api.github.com/graphql": Forbidden`**. **No PR was created** by this command. Git read/push works; GitHub API access remains unavailable. As permitted by Issue #2, the complete implementation branch and reviewable PR body are left pushed for creation through ChatGPT/GitHub. Manual creation: https://github.com/miragesu/sut-reservation-management/pull/new/feat/day2-coordination . No credential values were inspected or copied.

## Remaining full-MVP / external gates

- Day 3 Dashboard Claim/Queue/Reserve modals, complete notification bell/desktop opt-in, broader UX/accessibility acceptance and final full-MVP sign-off are unimplemented/unverified. Complete notification/modal refresh criteria remain unchecked even though Day 2 supplies the shared live Detail/Inbox controller and recipient-scoped persistence.
- Actual internal Linux host, trusted LAN firewall/two browser clients, production backup/restore rehearsal and hosted GitHub Actions are unverified. Local cloud tests do not establish those outcomes. A source-free remote-context smoke on the existing cloud daemon is distinct from a newly provisioned production OS.
- Full MVP is **NOT DONE**. No production data/secrets or hardware access-control behavior is introduced.
