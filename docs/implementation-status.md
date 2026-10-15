# Current implementation status — DEP-007 / Issue #6

**Registry release / production acceptance: NOT DONE.** Started from latest main `3b59e2e` on `feat/dep007-dockerhub-release`. Day 3/DEP-006 is now merged; its historical verification is retained below.

Implemented the version-tag Docker Hub release workflow, mandatory successful regression/candidate deployment checks before pushing, main ancestry/SemVer guards, official SHA-pinned actions and scoped GitHub Secrets references. Post-push validation uses an empty Docker credential directory to test anonymous published-digest pull and deployment. No release tag, registry push or production deployment is claimed.

Primary operators use image-only `compose.deploy.yaml` and a private SECRET_KEY. GitHub Remote Build remains optional. Host **5088 → Container 80**, UID10001, zero capabilities/no-new-privileges, private namespace sysctl80, migrations, SQLite named volume and all application behavior remain. Administrator setup/update/provenance/backup/restore/rollback: [deployment guide](deployment.md). Acceptance map: [DEP-007 verification](dep007-verification.md).

| Check | Observed result |
| --- | --- |
| Ruff check/format, compileall, official actionlint 1.7.7 (checksum verified) | PASS |
| Full pytest | **122 passed** (103 retained + 19 release-ref cases), 86.68s; one TestClient deprecation warning |
| Baseline / Day 2 / Day 3 Chromium | All PASS |
| Source Docker build/full Compose runner | PASS, exports a locally loaded validation image; no registry push |
| Image-only Compose in source-free temp directory, --no-build | PASS: actual 5088→80, UID/capabilities/sysctl, migrations/login/browser, data/session persistence, deadline recovery/dedupe and independent-volume cold restore |
| Image-only rerun with Git unavailable | PASS |
| Required image / SECRET_KEY missing | Both fail closed; valid image-only config needs no Git ref/build |
| Optional latest-branch GitHub Remote Build | **PASS** at implementation SHA `c6c3065158f088ff3c8224ef2177b7f6d7882e0a`, complete source-free Compose/5088:80/privilege/login/background/persistence/backup-restore runner |
| Hosted application CI | **PASS** at implementation SHA `c6c3065`: [run 38744064962](https://github.com/miragesu/sut-reservation-management/actions/runs/38744064962), public conclusion SUCCESS, **5m 10s**. Runs all pytest/browser/source-build and image-only deployment checks; this is not a version-tag publishing run. |
| Docker Hub version publishing / anonymous public pull | NOT RUN: no authorized release version/tag selected; cloud has no registry credential bindings, GitHub secrets metadata query returns Forbidden and Docker Hub metadata tunnel returns Forbidden |

GitHub Secrets may exist remotely but cannot be verified through the blocked API. The owner must securely configure/verify DOCKERHUB_USERNAME=mirage315 and a scoped DOCKERHUB_TOKEN, public repository visibility, then publish an explicit reviewed version tag after merge. Never supply token values in chat/source/server configuration. A successful loaded-image test is not evidence of a public Docker Hub release.

Implementation branch is pushed at `c6c3065158f088ff3c8224ef2177b7f6d7882e0a`; delivery metadata commits change documentation only. Actual creation attempt:

```bash
gh pr create --repo miragesu/sut-reservation-management --base main \
  --head feat/dep007-dockerhub-release \
  --title 'DEP-007: versioned Docker Hub releases and image-only deployment' \
  --body-file docs/dep007-pr.md
```

returned **`Post "https://api.github.com/graphql": Forbidden`**. **No PR was created.** The pushed branch and [PR body](dep007-pr.md) remain available for connected GitHub tooling: https://github.com/miragesu/sut-reservation-management/pull/new/feat/dep007-dockerhub-release . Company LAN access, separate production Linux server, firewall/two-client access and production restore/cross-version rollback remain unverified. No production data/secrets or hardware-control code is added.

---

# Historical implementation status — Issue #4 / Day 3

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

## DEP-008 — Administrator deployment documentation (2026-10-15)

Based on main `5ebb4f62c30812d67c0383c0a426bdd0ea862796`, branch
`docs/dep008-admin-deployment`. Primary `compose.deploy.yaml` now uses long-form
bind `/data/sut-reservation-data` → `/app/data`, refusing silent source creation.
Existing Named Volumes are untouched. Optional Remote Build retains its historical
Named Volume. Application source, Dockerfiles, entrypoint, migrations and published
image are unchanged; no image rebuild/republication was performed.

README contains the A–H Linux quick start; deployment.md adds initial web operation,
private random secret generation, persistent filesystem checks, cold backup with
WAL/SHM/ownership, empty-directory restore/integrity, upgrades/compatible rollback,
manual old-volume migration, and troubleshooting. AGENTS/SPEC/PLAN/decisions record
DEP-008's explicit supersession of primary production Named Volume requirements.
The old v1.0.0 tag contains historical Compose; the guide requires a reviewed
DEP-008 source SHA for the deployment file while using the unchanged image digest.
Smoke helpers were updated solely to isolate test bind storage and discover the
actual backup mount; runtime application behavior is unchanged.

### Observed verification

| Check / command | Actual result |
| --- | --- |
| `docker compose -f compose.deploy.yaml config --quiet` and JSON assertions (generated test key, never printed) | PASS on Compose v2.40.3: exact production bind source/target, no top-level volume/build, 5088:80, UID10001, capability/deadline/restart settings retained. Rendered JSON omits false `create_host_path`; YAML explicitly sets false. |
| Temporary missing-source deployment, using existing image and isolated project | PASS: fails with `bind source path does not exist`; source is not created and app never starts. No real `/data` access. |
| `.venv/bin/pytest -q` | **122 passed, 1 warning in 123.61s**. Existing Starlette/httpx deprecation warning is non-failing. |
| `.venv/bin/ruff check backend scripts`; `.venv/bin/ruff format --check backend scripts` | PASS; 52 files formatted. |
| `bash -n` for every README/guide Bash block; local Markdown target checks; `git diff --check` | PASS. Syntax/static validation does not claim execution of commands against production. |
| `DOCKER_CONFIG=/tmp/sut-v1-release-anonymous SUT_SMOKE_IMAGE=mirage315/sut-reservation-management@sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6 SUT_SMOKE_PULL=1 .venv/bin/python scripts/container_smoke.py` | PASS, exit 0: anonymous pull of published image, source-free image-only Compose, temporary bind directory, actual **Host5088→Container80**, UID10001/capabilities/NoNewPrivs/port79 denial, startup migrations, bootstrap/forced-password/login/Chromium Dashboard/Table/Detail/My Usage, session/data persistence across down/recreate, Claim/Release/FIFO/history, live/offline deadlines and restart idempotency. No build. |
| Runtime mount and filesystem inspection during smoke | PASS: `bind /tmp/sut-compose-7w5zc403/data -> /app/data`; directory UID/GID 10001:10001, mode700, sut.db created. Only source path is substituted for isolation; static check verifies literal `/data/sut-reservation-data`. |
| Cold backup/restore portion of same smoke | PASS: source bind archive restored to separate empty disposable recovery Named Volume; sessions/history/notices/ownership, SQLite integrity/foreign keys and Alembic check preserved. A host bind-directory restore remains an operator rehearsal, not claimed by this test. |

The first configuration assertion failed because Compose omits false boolean keys;
the assertion was corrected to accept omitted false, and the full image smoke then
passed. No deployment setting was weakened. Only generated synthetic test storage
was cleaned up; no production path or preexisting volume was mounted or migrated.

### Published image evidence (release operation preceding DEP-008)

v1.0.0 source is `5ebb4f62c30812d67c0383c0a426bdd0ea862796`;
[release run 38746750990](https://github.com/miragesu/sut-reservation-management/actions/runs/38746750990)
**SUCCESS**, 8m23s, includes tests/build/Compose/login/push/anonymous digest deployment.
Published and independently anonymously pulled immutable reference:
`mirage315/sut-reservation-management@sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6`.
Earlier DEP-007 publication-pending entries are historical, superseded by this
observed release; separate production-server acceptance remains pending.

### External checks still required

No real server was modified. Production persistent `/data` filesystem capacity,
mount-at-boot ordering, host UID mapping/SELinux policy, actual host5088 firewall and
two LAN browsers, first-time administrator workflow with real inventory, production
backup/off-host protection, empty bind-directory restore rehearsal and owner signoff
remain unverified from cloud. Full MVP production acceptance is **not declared**.

### DEP-008 delivery

Implementation commit `454cb5b` pushed to `docs/dep008-admin-deployment`.
`gh pr create --repo miragesu/sut-reservation-management --base main --head docs/dep008-admin-deployment --title 'DEP-008: administrator deployment guide and persistent bind mount' --body-file /tmp/dep008-pr.md`
failed with exact error: **`Post "https://api.github.com/graphql": Forbidden`**.
No PR was created or merged. The pushed branch is retained; the reviewable
[PR body](dep008-pr.md) can be used to
[create the PR manually](https://github.com/miragesu/sut-reservation-management/pull/new/docs/dep008-admin-deployment).
This subsequent delivery commit only records the result and PR body. Hosted CI
for this branch is not substituted for the locally observed verification above.

## DEP-009 — Installer, optional password mode and version promotion

Base main `79a6303`, branch `feat/dep009-setup-password-mode`; Issue #9 and all
existing confirmed BR-001–BR-028 preserved. No new release tag, Docker Hub push,
alias promotion, production host change or Named Volume migration was performed.

Implemented shared password policy with strict true/false parsing, default12 or
opt-in1-character minimum, maximum 128, nonblank requirement and no composition
rules. Backend provision/reset/change/bootstrap and HTML/CLI prompts agree.
SECRET_KEY validation is unchanged; hashing/rate limits/CSRF/RBAC/session revocation
and forced first-login password change remain active. The existing1.0.0 image is
explicitly prevented from claiming support for LOW_SECURITY_PASSWD.

`setup.sh` uses a fixed full Compose source commit and embedded SHA256. Operators
choose stable/latest/explicit version, confirm missing-alias1.0.0 fallback, and see
the actual version/digest before installation. Failed registry lookups do not silently
fall back. A private local digest lock prevents tag movement on reruns. The installer
checks platform/Docker/mount/disk/port, generates and retains a96-character secret,
uses the existing bind with0700/10001 ownership, refuses missing/mismatched existing
storage, and never migrates volumes. Explicit upgrades stop writers, snapshot record
IDs, make a cold backup before replacement and verify retained records plus
health/ports/mount/migrations/integrity. No automatic downgrade is attempted.

Primary Compose now exposes SUT_VERSION with stable default; optional source-build
Compose also forwards the password setting. All port/security/deadline behavior is
retained. Private installer output is ignored by Git and Docker build contexts.

Release configuration refuses existing explicit versions (registry errors fail
closed), promotes only validated official digests to latest after anonymous published
pull/deploy, and promotes stable solely through explicit main workflow dispatch,
`STABLE_PROMOTION_ENABLED=true` plus protected `dockerhub-stable` environment review,
then another anonymous deployment before login/promotion. Environment/reviewer
configuration and actual publishing remain external operations. OCI provenance,
version/source/digest summary and serialized release concurrency remain in place.

### Observed verification

| Check | Actual result |
| --- | --- |
| `.venv/bin/pytest -q` | **196 passed, 1 warning in 105.75s**. Existing Starlette/httpx TestClient deprecation warning only. Includes74 new cases for policy boundaries/roles/reset/change/bootstrap/secret/Boolean, registry tag refusal/error handling and real Bash function execution with disposable files/command doubles. |
| Ruff lint/format | PASS, 57 files. |
| `bash -n setup.sh`, documentation Bash blocks/local links, `git diff --check` | PASS. |
| `/tmp/actionlint-1.7.7 .github/workflows/release.yml .github/workflows/day1.yml` | PASS. Does not claim remote release jobs ran. |
| Compose config/JSON for stable/latest/1.0.0/1.0.1 | PASS: expected repository:version, no build, literal `/data/sut-reservation-data`→`/app/data`, no named production volume, UID10001,5088→80, default LOW_SECURITY_PASSWD=false, deadlines enabled. |
| Native baseline Chromium | PASS: login/forced replacement,2 Labs/20 fictional SUTs, filters/layouts/polling/stale-retry/profile. |
| Native Day2 Chromium | PASS: multi-user Claim/Release/FIFO/force-release/estimate/booking/check-in/history/Inbox and30s Detail polling. |
| Native Day3 Chromium | PASS: Card/Table actions, poll/input retention, conflicts, Taipei booking, keyboard/mobile and notification fallback/read. |
| Final Docker source build/default-mode full smoke | PASS, exit0: `DOCKER_CONFIG=/tmp/sut-v1-release-anonymous SUT_BUILD_NETWORK=host SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_SMOKE_EXPORT_IMAGE=mirage315/sut-reservation-management:ci-dep009 .venv/bin/python scripts/container_smoke.py`. Build TLS/hash checks retained;5088→80, UID10001,zero capabilities,NoNewPrivs,port79 denied, migration/bootstrap/login/Chromium, persisted sessions/data, live/offline deadlines, restart deduplication and independent cold recovery/integrity all passed. Local image only, no publication. |

Final image-only low-mode and installer lifecycle results are recorded below when
completed. Initial test-double/fixture failures were diagnosed rather than bypassed:
upgrade mock lacked the new record snapshot; direct-SQL fictional Lab fixture lacked
required description/created_at. Both fixtures were corrected without relaxing
production checks. A dynamic HTML label was corrected and final runtime source was
rebuilt and checked. Earlier passing results are not substituted for the final run.

### Remaining external gates

Only 1.0.0 is currently verified published and does not implement this new password
mode. Tentative1.0.1 must follow PR review/merge and a separate approved release.
No stable/latest availability or actual promotion is claimed. Configure protected
stable environment/reviewers and explicit enable variable before promotion; repository
owners retain publishing credentials only in Actions secrets. A real production
persistent /data mount and reboot ordering, host UID/SELinux, firewall/two LAN clients,
real administrator inventory workflow, disk/backup sizing and bind-directory restore
rehearsal remain unverified. Full MVP production acceptance is not declared.
