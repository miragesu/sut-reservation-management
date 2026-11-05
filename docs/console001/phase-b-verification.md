# CONSOLE-001 Phase B verification — 2026-11-05

Implementation scope and provisional choices:
[Phase B report](phase-b-implementation.md). Base main:
`80b8033c8684b264b73d2d07910c3acef178f6a0`.
All execution below used disposable synthetic databases, accounts, credentials and
local test containers. No production Server/SQLite/Client/BMC was contacted.

## Actual results

| Check | Actual result |
| --- | --- |
| Locked dependency installation | PASS; Python3.12.14, hash-checked requirements; only cryptography46.0.7 added, all prior locked versions unchanged |
| `ruff check backend scripts` | PASS, Ruff0.17.0 |
| New-source `ruff format --check` | PASS |
| `pytest -q` | **304 PASS**,1 preexisting Starlette/httpx deprecation warning,83.13s |
| New Console test collection | **87 cases** in the two Console test files; included in the304, not additional to it |
| Fresh and populated migration / `alembic check` | PASS; console001_b01 after c2026101601,13 new tables empty after upgrade, all old rows preserved, no automatic inventory BMC import |
| Integrity/FKs / guarded downgrade / backup restore | PASS; integrity_check=ok, foreign_key_check empty, populated Console downgrade refused, compatible pre-upgrade backup restored into separate empty directory |
| `python scripts/browser_smoke.py` | PASS: login, forced password change, seeded Dashboard/layouts/sort/polling/error recovery/detail/profile |
| `python scripts/browser_day2.py` | PASS: multi-user Claim/Release/FIFO, estimates, booking/calendar, manual start, history/inbox/polling |
| `python scripts/browser_day3.py` | PASS: Card/Table quick actions, input-preserving polling, conflicts, Taipei times, mobile and notification fallback |
| Local Docker source build + `scripts/container_smoke.py` | PASS: migrations,5088→80,UID10001,capabilities dropped,NoNewPrivs,listener,health/login, coordination/deadlines, restart/recreate persistence, Chromium and cold-volume recovery |
| Final local Docker build | PASS, image `sut-console001-b:final`, ID `sha256:89a531ad12303499fbf8f013c8569fc77a877f98c7d3b6e272f3d139ec1d8579` |
| Final image-only Compose smoke, LOW_SECURITY_PASSWD=true | PASS: source-free Compose-only directory, bind storage,5088→80,non-root/security,auth/deadlines/persistence and cold recovery; locally built image, **no public-registry pull** |
| `python scripts/installer_smoke.py` | PASS using local tested image: fresh/rerun/low-mode bootstrap/cold-backup upgrade, SECRET_KEY/config/admin/Lab preservation,health/migration/5088:80/bind assertions |
| `bash -n setup.sh` | PASS; installer source/checksum/Compose unchanged |
| Documentation/artifact checks | PASS:88 relative Markdown links, changed Python ASTs, no private-key/DB artifacts; `pip check` reports no broken requirements |
| Diff/owner ledger | PASS `git diff --check`; Q1–Q83/C1/C2 file unchanged, no production DB/key artifacts |

The latest whole304-case suite includes the final keyring-outside-SQLite-directory
check. Three Chromium runners and source-deployment checks ran with Console OFF;
metadata-on tests use an isolated synthetic fixture. The final local image-only
run includes all final application changes. Installer smoke used the earlier
locally tested `sut-console001-b:local` build of the same foundation; the last
subsequent change only hardened enabled-Console keyring path separation (Console
remains OFF in deployment/installer tests). No claim of an anonymous Docker Hub
pull, new release or installation on a real operator server is made.

## Commands used

A temporary venv under `/tmp/console001-b-venv` supplied the locked tools; abbreviated
below as `python`, `pytest`, `ruff` and `alembic`:

```sh
pip install --require-hashes -r backend/requirements-dev.txt
ruff check backend scripts
ruff format --check backend/app/models/console.py backend/app/services/console \
  backend/app/schemas/console.py backend/app/routers/api/console.py \
  backend/tests/test_console_foundation.py backend/tests/test_console_migration_crypto.py
pytest -q
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
bash -n setup.sh
```

Migration/schema checks also used a new scratch DB only:

```sh
DATABASE_URL=sqlite:////tmp/console001-b-schema.db alembic -c backend/alembic.ini upgrade head
DATABASE_URL=sqlite:////tmp/console001-b-schema.db alembic -c backend/alembic.ini check
```

The source/deployment runner receives existing session proxy/CA trust. Endpoint
selectors were cleared and the local Unix Docker daemon verified; registry config
was preserved. Neither TLS verification nor host-network restrictions were bypassed:

```sh
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
SUT_SMOKE_EXPORT_IMAGE=sut-console001-b:local python scripts/container_smoke.py

docker --host=unix:///var/run/docker.sock build \
  --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t sut-console001-b:final .

SUT_SMOKE_IMAGE=sut-console001-b:final SUT_SMOKE_LOW_SECURITY=1 \
  python scripts/container_smoke.py

SUT_INSTALLER_TEST_IMAGE=sut-console001-b:local python scripts/installer_smoke.py
```

Buildx state used a writable `/tmp/console001-b-buildx`; no DOCKER_CONFIG/credentials
were replaced. Published5088 was bound to local loopback in disposable smoke
projects. Each runner cleans up its own synthetic resources, not production volumes.
Installer preflight/registry/download transport are deliberately simulated by its
existing harness; unit tests cover their failures/contracts. It does not touch real
`/data`, production secrets, registry aliases or persistent operator configuration.

## Acceptance coverage

- Strict flags/policy, OFF denial, HTTP opt-in, CSRF/Origin and first-login gate.
- Admin metadata scope, same-Lab and retained-binding IDs, normalized name/global
  IPv4 uniqueness, disabled choices/slots, archive/restore/reenable collisions,
  append-only mapping/audit and immutable host-key/grant creation records.
- Independent UART/BMC save/clear/revisions, fixed22, RFC1918/private-sensitive-self
  classification, no target probe, exact impact generation binding, stale previews,
  scoped epochs and pending durable revocation metadata.
- Policy matrix for Claim/Admin/nonholder, inactive/expired/password-change states,
  grants, Normal transition, independent rights/read-only fallback, expiry boundary,
 24h extension ceiling, idempotent audit, fresh grant and preservation of ordinary
  coordination/notification counts.
- Eleven simultaneous quota allocators produce exactly10 successful reservations
  and one429; mixed UART/BMC quota, same-slot reconnect, stale-close/ticket rejection,
  single use, login deletion without FK breakage and expired-slot recovery.
- AES-GCM decryption/tamper/AAD/method binding, KEK rewrap, wrong/missing key, private
  keyring permissions/symlink/path/key separation, saved credential/API/log projection
  non-disclosure, stale evidence retaining old credential and replacement generations.
- Default production validation boundary always503; no `verified` request bypass,
  test-validator environment toggle, terminal route, generic exec API or actual SSH.

## Limits and remaining gates

These results do **not** establish SSH authentication/host trust, read-only terminal
byte enforcement, live revocation/fencing/outbox delivery, real quotas on sockets,
Broker IPC privilege separation, Console UI, WS/WSS or a production pilot. Public
registry publication/pulls, hosted post-push CI, Remote Build of the new branch,
actual company LAN/firewall/Client privileges, real key backup custody and production
recovery are **not verified** here. No real host checks were authorized.

C3 remains mock-feasible but actual account/socket review is open. C4 plaintext
HTTP/WS risk requires explicit operator acknowledgement and LAN controls. C5 needs
independently verified fingerprints and operational risk signoff. A1–A15 choices
remain provisional as enumerated in the implementation report. Phase C needs an
explicit separate instruction after review, not automatic continuation from this PR.

## GitHub delivery

Implementation commit `f5b274ec808de2d6cd35beae672006d1fba1af8c` was pushed to
`feature/console001-phase-b` and its remote ref verified. PR creation targeting
main was attempted and failed with the exact error:

```text
Post "https://api.github.com/graphql": Forbidden
```

No PR was created by Codex, no merge or Phase C start occurred. The pushed branch,
[reviewable PR description](phase-b-pr.md) and
[comparison/manual creation link](https://github.com/miragesu/sut-reservation-management/compare/main...feature%2Fconsole001-phase-b?expand=1)
are retained. Hosted post-push CI remains unverified; local passing checks above
are not represented as a hosted run result. The delivery-only follow-up changes
Markdown, not the tested application or image contents.
