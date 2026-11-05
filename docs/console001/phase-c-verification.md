# CONSOLE-001 Phase C verification — 2026-11-05

Status: local Phase C backend verification PASS; ready for code/security review.
Production and Phase D/E gates below remain open.
Base main: `c54948a0ad6f8c76761d9bc594147aec73775d70`.
Branch: `feature/console001-phase-c`.
[Implementation, contracts and remaining risks](phase-c-implementation.md).

All accounts, passwords, keys, SSH endpoints, terminal tokens and SQLite data were
synthetic/disposable. No company host, production SQLite, real BMC/Client, real SSH
keys or tmux/minicom was accessed. No image was pushed/published. Local Docker
names are test artifacts, not public Docker Hub releases.

## Executed checks

| Check | Actual result |
| --- | --- |
| Existing baseline before Phase C tests | 304 PASS |
| New Gateway/IPC unit integration | 33 PASS; explicitly FakeSSH, real Unix socket and SQLite |
| Final whole pytest | **337 PASS**,1 preexisting Starlette/httpx deprecation warning,117.31s; includes304 baseline +33 new Gateway cases |
| Ruff / new-source formatting / bash syntax / dependency consistency | PASS; `ruff check backend scripts tests/console_mock`;23 new/related formatted Python files; `bash -n setup.sh`; `pip check` |
| Chromium Day1 / Day2 / Day3 | All3 PASS; native Chromium, existing coordination/UI workflows, Console OFF |
| Source build + Compose container smoke | PASS;5088→80,UID10001,zero caps,NoNewPrivs,port79 denial,migrations,coordination/deadlines,persistence,Chromium,cold backup/recovery |
| Final image-only low-security Compose | PASS; final verified local image, no source/build, health/migrations/5088→80/non-root/persistence/cold recovery |
| Installer fresh/rerun/backup-upgrade regression | PASS; final verified local image, config/SECRET_KEY/admin/Lab preserved; no secret output |
| Disposable real SSH/tmux/BMC + private Broker + HTTP/WS | PASS; final source image rerun, real HTTP/WS/SSH and distinct UIDs/mounts |
| Owner ledger / links / artifacts / diff whitespace | PASS;90 relative Markdown links, identical Q1–Q83/C1/C2 file, no staged key/DB/env artifacts, diff whitespace clean |
| Hosted branch CI / branch Remote Build / real-device/LAN | Not yet verified; never inferred from local tests |

## Reproduction

Use Python3.12, hash-checked requirements-dev in a disposable venv. The working
venv was `/tmp/console001-b-venv` (name reused; dependencies installed from the new
locks). Commands:

```sh
pytest -q
ruff check backend scripts tests/console_mock
ruff format --check backend/app/console_broker backend/app/services/console \
  backend/app/schemas/console_live.py backend/app/routers/api/console_live.py \
  backend/tests/test_console_gateway.py scripts/console_mock_smoke.py tests/console_mock
bash -n setup.sh
python -m pip check
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
```

Docker selectors were cleared and the local `/var/run/docker.sock` daemon checked.
Existing registry/proxy config was preserved; writable Buildx state in
`/tmp/console001-c-buildx`, normal CA trust supplied as BuildKit secret. No TLS
verification disablement, host networking or production mount was used:

```sh
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
SUT_SMOKE_EXPORT_IMAGE=sut-console001-c:local python scripts/container_smoke.py
SUT_SMOKE_IMAGE=sut-console001-c:verified SUT_SMOKE_LOW_SECURITY=1 \
  python scripts/container_smoke.py
SUT_INSTALLER_TEST_IMAGE=sut-console001-c:verified python scripts/installer_smoke.py
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt python scripts/console_mock_smoke.py
```

The installer harness intentionally simulates host mount/preflight/registry download
transport and uses a local tested image and disposable directories. It does not
validate real `/data` boot ordering, public registry release or a company install.

## Actual mock topology and observations

`tests/console_mock` and `scripts/console_mock_smoke.py` are reproducible fixture
sources. The script creates one internal Docker network with no published ports:

- Root **fixture only**: OpenSSH22 and blackhole2224, generated Ed25519 host key,
  synthetic fixed account UID11000, runtime-random password and passphrase-encrypted
  key; two already-created default-socket tmux sessions `existing` and `other`.
  Each runs synthetic raw UART echo, not hardware/minicom. Forwarding disabled.
- Non-root probe UID10002: actual production SSHTransport against fixture, no caps,
  read-only image, no-new-privileges. Host pin compared independently.
- Broker UID10002: actual CLI, read-only image, no caps, no-new-privileges; only
  private IPC and independent0600 KEK mounts. No database mount or public listener.
- Gateway UID10001: read-only image, no caps, no-new-privileges; IPC read-only mount
  and synthetic DB mount, **no KEK**. Actual HTTP/CSRF/login/one-use-ticket/WS flow
  on loopback8080 inside its own container, calling the separate Broker by UDS.
- Broker SIGKILL/start: owned stale socket recovered; a fresh explicit IPC/SSH
  connection works. Original tmux session names remain exactly existing/other.
  Only this invocation's containers/network/volumes are deleted.

Actual first full pipeline versions: OpenSSH9.2/OpenSSL3.0.22, tmux3.3a,
AsyncSSH2.23.1, Python3.12; local daemon28.4.0. Exact versions are printed on rerun.

| Real isolated observation | Result |
| --- | --- |
| Discovery rejects host before authentication; independent fingerprint matches | PASS |
| Unknown pin / deliberately wrong public key / wrong password | PASS, sanitized refusal |
| Password and passphrase-encrypted private-key authentication | PASS |
| Exact configured existing tmux / two concurrent writers and readers | PASS |
| Native Ctrl+B then D → ordinary fixed-account shell, xterm-256color | PASS |
| PTY resize37×111 verified with synthetic shell `stty size` | PASS |
| Close one SSH attachment; other writer remains usable | PASS |
| Missing tmux session | PASS: tmux_not_found, original two names unchanged, no shell |
| Direct mock BMC shell; loopback target / non22 BMC port rejected | PASS |
| Real blackhole SSH establishment | PASS:9.5–12s observation for10s timeout |
| UID10001→authenticated IPC→UID10002 Broker→OpenSSH/tmux | PASS |
| Encrypted Client envelope reused, real input/output, fence ACK blocks more input | PASS |
| Generic exec/forward/SFTP private operations absent | PASS |
| Distinct mounts: no DB in Broker; no KEK in Gateway | PASS |
| Real HTTP/CSRF/login→challenge/OOB ack→validated create→ticket→WS→Broker→SSH | PASS |
| Real WS input ACK and binary terminal echo, intentional Disconnect | PASS |
| SQLite dump excludes plaintext SSH/login passwords and terminal marker | PASS |
| Broker hard termination/restart, fresh attachment, original tmux survives | PASS |

Native tmux prefix testing uses human-separated Ctrl+B and D; a single immediate
paste-like burst can invoke tmux's existing assume-paste behavior. The Gateway does
not reconfigure that behavior. Synthetic shell observations are not real UART/BMC
compatibility, application commands or production privileges acceptance.

## Gateway/transaction evidence (FakeSSH, not real hardware)

Tests distinguish protocol/SQLite concurrency from SSH implementation:

- Verified candidate, encrypted stored projection, auth-only/no PTY on pre-save;
  failure/changed key withholds credentials and retains old active connection.
- Ticket single-use/replay/login/tab/expiry binding; forged Origin, generic exec
  frames, unauthorized mutation and secret-reflecting validation errors denied.
- Twelve concurrent live API reservations yield exactly10 successes/two429s.
- Independent Gateway+Broker read-only denial; `-r` promotion requires manual
  reconnect, no silent ignored writable input.
- Claim Release, maintenance grant revoke, mapping clear, Client trust replacement
  and BMC trust replacement fence affected generations; opposite transport stays
  usable. Delivery timestamp only after Broker ACK.
- Pending open cancellation ACK/tombstone rejects late open, Broker lease expiration,
  IPC HMAC/peer UID/replay and operation allowlist.
- Explicit new Connect after Broker boot change, no input replay, transient same-slot
  generation retry and deliberate Disconnect during backoff cancels future attempts.
- Unrelated mutation preserves pending SSH; failed candidate preserves live terminal.
- BMC3-attempt flow, new flow succeeds, credential canary absent from DB metadata.

The existing304-case suite also covers all three policies, grant expiry/alternative
rights, quota allocator races, schema/history/encryption/backup integrity and the
coordination BR regressions. These are not additional tests on top of the final
whole-suite count. No schema migration added; head stays console001_b01.

## Remaining limits and rollout gates

No physical UART/minicom, vendor BMC, custom/other-owner tmux socket, actual
intranet browser transport, real key backup rotation, sustained load/fuzz or
company LAN/host boot/storage was exercised. Ten-slot tests are concurrency tests,
not a capacity certification. Revocation uses a trusted single Gateway worker and
short independent Broker leases; no distributed-worker guarantee.

Shared fixed SSH account gives ordinary Linux shell authority; native commands can
alter sessions. No per-SUT confinement or remote per-RD command attribution is
claimed. HTTP/WS opt-in exposes browser-hop credentials/terminal/cookies plaintext;
C3/C4/C5 and privilege/segmentation/TLS review remain required before any pilot.
A1–A15 are engineering assumptions, not newly approved owner policy. Full Phase D
UI and Phase E production rollout are not implemented or automatically started.

## Issues found and corrected during validation

The first real SSH fixture found the missing bcrypt extra needed for encrypted
OpenSSH private keys; it was added and both password/key paths rerun successfully.
The real UART fixture also reproduced tmux's native paste/key-timing behavior;
the human-keybinding test now separates prefix/detach without changing tmux config.
Initial new test assertions were corrected to the existing Claim201/Release
usage_key contract and429 quota response; application coordination contracts were
not changed to fit tests.

A whole-suite run exposed cancellation between the Failed state and browser close,
which could leave logical quota until lease expiry. ASGI cleanup is now shielded
with a5s bound, closes local quota/flow metadata before reconciliation, and leaves
only unacknowledged delivery pending if IPC fails. Subsequent Gateway cases pass.
Final review also rejected mismatched extra fields with a validation_id rather
than silently ignoring a different IP/secret/enable flag. A replacement/single-use
candidate regression covers this. There is no remaining known failing acceptance
case hidden by a skip/xfail; untested production cases remain listed separately.

Final locally built image: `sut-console001-c:verified`, image ID
`sha256:40103b66e53517fac5952372b802b967d423805142898a3bf6f9405554ddac37`.
This is a local image ID, **not a published registry digest or release**. Final
image-only Compose, installer and real SSH pipeline use this final application
code, including cancellation-safe cleanup and exact validated-candidate guards.
All preexisting runtime dependency pins are preserved; only AsyncSSH2.23.1,
bcrypt5.0.0 and websockets15.0.1 are added. The bcrypt extra is SSH key support,
not a replacement for application Argon2id hashing.
