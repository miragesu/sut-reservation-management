# CONSOLE-001 Phase E — actual verification

Date:2026-11-05. Base main **00776f9b4b3bd4b7ee468899a9832b1036c1afd8**
(merged Phase D), branch `feature/console001-phase-e`.
[Implementation](phase-e-implementation.md), [operator runbook](operator-runbook.md),
[rollback/recovery](rollback-and-recovery.md).
Q1–Q83/C1/C2 ledger SHA256 remains
`10e6473a2021e79f65c413f3037ebba8a14ca58be1502a2e4fb9199aeca624a2`.
No company host, Console Client, BMC, UART, production SQLite/credential, Docker Hub
publication/promotion, release tag, deployment activation or merge was used.

## 1. Completed and verified in isolated tests

| Check | Actual result |
| --- | --- |
| Complete pytest | **358 passed**, one existing TestClient deprecation warning,143.13s. Baseline346 +10 deployment/crypto cases +2 installer guard cases |
| Additional atomic-failure rewrap assertion |10 targeted deployment cases pass after adding mid-batch corruption rollback proof; first rewrap rolls back, prior crypto revision/audit retained |
| Ruff check/format |PASS,99 Python files formatted |
| Shell syntax |PASS: setup.sh and scripts/entrypoint.sh |
| JavaScript module syntax / pinned vendor integrity |PASS; Phase D code/assets unchanged |
| Official actionlint1.7.7 |PASS on updated application workflow; downloaded archive checksum verified, shellcheck integration disabled (shell snippets checked separately) |
| Python dependency consistency |PASS, no broken requirements |
| Three retained Chromium suites |All PASS: baseline login/mandatory change/dashboard/polling/profile; Day2 coordination/queue/calendar/history; Day3 modals/mobile/notification fallback |
| Actual isolated SSH/Broker/Gateway + Console Chromium |PASS: existing real mock SSH/PTY/tmux/BMC transport suite plus **34 Console browser checkpoints** from Phase D, including shared writers/RO/quota/revocation/host keys/private-key replacement/paste/search/fullscreen/fonts/resize/non-persistence |
| Source Docker build + container Compose |PASS:5088→80, UID10001, zero capabilities/no-new-privileges, low-port boundary, migrations, deadlines, Chromium, persistence and independent cold restore |
| Ordinary image-only Compose |PASS: locally loaded regression image, no source/build in deployment directory; low-password mode included; data/session/deadline and cold backup recovery pass |
| Actual installer lifecycle |PASS: fresh/low-mode bootstrap/rerun/cold-backup upgrade; config/SECRET_KEY/admin/Lab preserved,5088:80/bind/migration/integrity, no secret output |
| New Console image-only deployment runner |Seven named checkpoint groups PASS; final independent-custody/fresh-install repeat passed |

New deployment checkpoint groups:

0. Console-on fresh installation uses a separate empty bind, completes migration
   before healthy and creates no default account; it never replaces the populated
   upgrade fixture.
1. Actual copied image-only Compose artifacts, Web10001/Broker10002/keeper10003,
   PID1 zero effective capabilities and no-new-privileges,5088→80, readonly roots,
   disjoint DB/KEK mounts and HMAC/peer-UID authenticated startup preflight.
2. Kernel namespace firewall: permitted mock SSH positive; sensitive private SSH,
   gateway/localhost/metadata and unapproved port rejected by **raw sockets**, not
   only API classification. Mock HTTP80 and sensitive mock SSH22 are independently
   reachable from the mock peer, so absence of a listener is not the negative proof.
   CIDR classification covers RFC1918 across unrelated Lab networks, invalid
   policy fails closed, BMC22/private-only and configured Client ports preserved.
3. Old-main image creates migrated synthetic users/password hashes, Lab,3 SUTs,
   active usage, queue, reservation and history. Phase E starts against that same
   persistent bind; exact business-table fingerprint/count/schema/integrity/FKs
   match, then recreate and empty-directory cold restore preserve them. An actual
   pinned mock SSH authentication seals a retained credential in Broker; restored
   Web preflight verifies its encrypted envelope with matching independent KEK.
4. The actual old-main image reads **its own pre-upgrade DB backup**, retaining the
   same account/usage/queue/reservation/history fingerprint; no old image is aimed
   at a potentially incompatible newer schema. No migration is added in Phase E.
5. Replace runtime KEK with a random same-ID syntactically valid wrong key:
   authenticated preflight rejects the retained envelope. Restore exact key backup
   and repeat preflight successfully. Final fixture backup is in a separate private
   directory mounted into **neither Web nor Broker**, not merely outside SQLite.
6. Missing explicit HTTP acknowledgement and unavailable Broker both reject actual
   deployment preflight. Unit/retained foundation cases additionally cover missing,
   permissive/symlink/wrong keys, AAD tampering, ciphertext retention, DB-transaction
   rollback, invalid policy and installer refusing a paired Console upgrade.

The source/image-only/installer runners use only their own disposable project,
volumes and bind directories. Console runner substitutes private temporary paths
for the production /data bind, shortens only its test health interval, and adds
synthetic SSH services on its own internal Docker network. It never contacts an
address outside the test environment. Fixture secrets use RAM/stdin, no checked-in
accounts/passwords/keys/DBs. No production path is modified.

### Reproduce

Python3.12.14, Docker28.4.0, Compose2.40.3, Chromium `/usr/bin/chromium`,
OpenSSH9.2/OpenSSL3.0.22, tmux3.3a, AsyncSSH2.23.1. Install locked dev requirements
in a disposable virtualenv and retain the managed proxy/CA trust if applicable.
Use a disposable local daemon; commands below delete only their own fixture data.

```sh
pytest -q
ruff check backend scripts tests/console_mock
ruff format --check backend scripts tests/console_mock
bash -n setup.sh scripts/entrypoint.sh
for file in backend/app/static/console-*.js; do node --input-type=module --check < "$file"; done
python -m pip check
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
docker build --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t sut-console001-e:local -t sut-console001-c:local .
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_CONSOLE_BROWSER=1 python scripts/console_mock_smoke.py
# Export the exact prior main tree into a temporary directory, then build it:
# git archive 00776f9b4b3bd4b7ee468899a9832b1036c1afd8 | tar -x -C "$previous_context"
# docker build --secret id=build_ca,src=... -t sut-console001-e:previous "$previous_context"
python scripts/console_deployment_smoke.py
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_SMOKE_EXPORT_IMAGE=sut-console001-e:regression python scripts/container_smoke.py
SUT_SMOKE_IMAGE=sut-console001-e:regression SUT_SMOKE_LOW_SECURITY=1 python scripts/container_smoke.py
SUT_INSTALLER_TEST_IMAGE=sut-console001-e:regression python scripts/installer_smoke.py
```

Application CI now builds the pinned prior source and runs the new deployment
runner after the existing actual mock/Chromium suite. This configuration is checked
locally; its hosted execution is **not** claimed here.

Local image IDs (not published registry manifests/digests):

- Console candidate `sha256:fb3aad4b8e26fdaf393f5748eb0db788b6d9a5e3197979e6f609b48f4448c3be`.
- Prior main `sha256:2db9ce85046487c13c74f50cd0cedd7e2722a3bb72ffe9645a21bef9806541aa`.
- Source regression `sha256:48beee7ff6eff0b5659d720ea45fbfa1a3734ccf559577513000b776866b580b`.

These are separate local build snapshots of the tested runtime and fixture/docs;
they do not imply Docker Hub publication or anonymous registry-pull success.

## 2. Implemented, awaiting real company LAN/Client/BMC testing

- UID/mount/namespace/policy/boot deployment on the actual Docker/kernel/SELinux
  host; complete host/NAT/Docker/control-plane exclusion inventory and LAN ingress.
- C3 real fixed SSH account privileges, default socket/owner/ACL, existing minicom,
  native Detach-to-shell, shared simultaneous users and process-preserving disconnect.
- Real BMC SSH algorithm/auth compatibility, real browser HTTP clipboard/permission
  behavior, remote account/network privilege scope and capacity/load.
- Production cold backup/independent key retrieval, power/reboot/missing-/data
  mount behavior and operator-driven paired upgrade/compatible rollback.

No synthetic result resolves these actual-host acceptance gates.

## 3. Requiring explicit operator approval before production

- **C3 OPEN:** account/socket/shell topology and shared identity consequences;
  no per-SUT OS confinement or reliable per-command attribution/transcript.
- **C4 OPEN:** deliberate HTTP/WS opt-in, explicit acknowledgement and LAN bind/
  firewall acceptance. Cookies, provisioning credentials, BMC passwords and shell
  stream are plaintext/interceptable; downstream SSH does not protect this hop.
- **C5 OPEN:** independently trustworthy Host Key distribution, RD verification
  training and residual mistaken/malicious RD trust acceptance. Audit/checkbox is
  not proof that a private SSH endpoint is actually a BMC or the intended Client.
- Review separate privileged namespace initialization, sensitive inventory,
  custodian/offline maintenance exception, image provenance, operator training,
  independent PR/hosted CI and separately authorized release/activation.

## 4. Not implemented or not verified

- Real TLS termination/trusted-proxy HTTPS/WSS end-to-end deployment is not tested
  or supplied here. UI scheme selection and exact-Origin contracts remain; the
  entrypoint rejects untrusted forwarded headers. No HTTPS/WSS production claim.
- No company-host pilot, physical UART/BMC, production restore/reboot, performance/
  HA/security certification, image CVE audit or external penetration test.
- No automatic full host inventory discovery, Lab allowlist or guarantee that all
  sensitive aliases were supplied; the operator must provide the complete deny
  policy. Web's base bridge is not an OS-level egress sandbox. Compromised host/
  root or authorized shared shell privilege remains beyond these controls.
- OS-native unload prompts, actual insecure-LAN clipboard permissions, extensions,
  password-manager behavior and forensic RAM erasure are not guaranteed. Phase D
  browser retry/clipboard denial injection boundaries remain as documented there.
- No published Console image/anonymous public pull, release/tag/latest/stable
  promotion, real deployment, automatic merge or next-phase execution.

## Development failures corrected

Initial namespace startup failed because a private0600 nonsecret policy was not
readable after cap_drop; the reviewed file-only policy mount is0644 within an
operator0700 parent. No secret permissions were broadened. Rollback fixture copying
initially lost UID10001 ownership; test restore now explicitly sets fixture
ownership before using the old image. Encrypted onboarding fixture initially used
an OpenSSH public-key line with a comment rather than the exact negotiated wire pin;
it now compares against the known synthetic fingerprint and uses the observed
canonical pin. No accept-any/TOFU bypass was added. Earlier failed attempts are not
counted as acceptance; final runners supersede them.

## Final repeat and GitHub delivery

Final independent-custody/fresh-install runner: **PASS, all seven checkpoint groups**.
Static documentation check:109 local Markdown links, vendor SHA256 manifest and
owner-ledger immutability PASS. All disposable runner commands exited successfully.
Branch push and one PR creation attempt will be recorded after final checks.
Release readiness: candidate for independent review only; C3/C4/C5 and all actual
production approval remain open. This is not full production acceptance.
