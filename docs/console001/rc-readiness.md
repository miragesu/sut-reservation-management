# CONSOLE-001 RC readiness review

Review date2026-11-05 (Asia/Taipei). Base main
`69b44960c0deaab007a43eaa4afd061804a430d6` (merged Phase A–E and PR18 backup-path
follow-up), branch `release/console001-rc-preparation`. **Documentation/readiness
only: no product, deployment, release configuration or owner decision changes.**

Disposition: ready to submit for independent review; **NO-GO for RC publication or
live pilot today**. R1 validation instability, exact-source hosted CI/release
approval and actual operator C3/C4/C5 gates remain open. See
[GO/NO-GO](release-go-no-go.md), [operator acceptance](production-acceptance-checklist.md)
and [staged pilot](pilot-plan.md). This review does not authorize the next step.

## Authoritative integration and conflicts

Reviewed complete Q1–Q83/C1/C2 ledger, current instructions/spec/plan/tasks,
compatibility/acceptance, Phase E evidence/runbook/recovery and the actual config,
Broker/Gateway/terminal/crypto/deployment/release/test paths. Owner ledger SHA256
remains `10e6473a2021e79f65c413f3037ebba8a14ca58be1502a2e4fb9199aeca624a2`.
Historical Phase A/B “not implemented” statements and root coordination-only
exclusions remain milestone records; their active Console exception comes from
the later owner decisions and merged B–E reports, not from rewriting BR-001–028.

C1 permits the fixed remote account's normal Linux shell after native tmux Detach;
no forced-command confinement or per-SUT OS isolation is required/claimed. Gateway
only auto-attaches existing sessions and never creates/kills/reconfigures tmux/
minicom. User shell operations may affect other remote files/processes/hardware;
no transcript means limited per-command attribution. C2 stays RFC1918 BMC IPv4,
fixed22, no Lab CIDR allowlist plus sensitive/self/metadata/host/container denial.
RD mappings and Host Key trust remain independent of Claim; Admin infrastructure,
three policies, shared writers and temporary grants are not silently narrowed.

A1–A15 remain engineering choices, particularly64-character default-socket names,
disabled-Client slot semantics, identity-preserving KEK rewrap and resource/lease
budgets. Actual Client compatibility and review remain required. X7 real TLS/WSS
is unverified, not silently marked complete by merged Phase E. C3/C4/C5 remain open.

## Version inventory and proposal

- Latest observed remote Git release tag: **v1.0.2**, annotated and peeled to
  `3b98e669a5c601ef3ead13092ff18fa67ba217dd`. v1.0.0 and v1.0.1 also exist.
  Current main above is an **unreleased Console integration**, not a published1.0.2.
- No centralized product version is set in source. FastAPI still has the historical
  “Day2” title and default API metadata version0.1.0, with OpenAPI/docs disabled;
  that is not the Docker/product release identity. Git ref, OCI version/revision
  and registry digest are the release authority. No metadata/UI version bump here.
- Propose **Git v1.1.0-rc.1 / Docker1.1.0-rc.1**: first backward-compatible feature
  increment after1.0.2, explicitly a candidate. It is not reserved, approved or
  created. Remote tag list has no proposed RC; anonymous registry manifest HEAD
  reported RC absent. Recheck both just before any separately authorized release.
- Source/version must be independently confirmed after this PR's review/merge.
  Do not silently tag a newer unreviewed main HEAD or assume this base is preapproved.

Anonymous registry manifest HEAD observations (not image pulls or provenance proof):

| Tag | Result / manifest digest |
| --- | --- |
| 1.0.0 | sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6 |
| 1.0.1 | sha256:9ff09cd2fb5ae1bff4854aba946dd9a61c170653e00730b658ad19255b6124d0 |
| 1.0.2 | sha256:367655e87ee5b71597a29b8520952a1898d498f1e3da1136c41850b28f3bdc13 |
| latest | sha256:367655e87ee5b71597a29b8520952a1898d498f1e3da1136c41850b28f3bdc13 |
| stable | absent |
| 1.1.0-rc.1 | absent |

latest currently equals1.0.2; stable is absent. Nothing was pushed or promoted.
Older README/DEP-009 “only1.0.0/planned1.0.1” statements are historical publication
snapshots, not this registry inventory. Actual company installed version is unknown.

Existing release workflow accepts vMAJOR.MINOR.PATCH[-prerelease], <=128-character
Docker tags, valid prerelease identifiers, no build metadata; requires main ancestry,
reusable checks, scoped DOCKERHUB_USERNAME/TOKEN, pinned actions, candidate tests,
explicit-tag absence, provenance/SBOM and anonymous published-digest deployment.
Prerelease skips latest; stable requires separate main-only dispatch, official
version, protected dockerhub-stable environment and enable variable. Secret/env
readiness and protected-reviewer configuration are not verified from source alone.

The coordination setup installer intentionally accepts stable/latest/official x.y.z,
not prerelease versions, and refuses an existing Console overlay. Controlled RC
installation uses reviewed image-only paired Compose and immutable digest, not a
silent setup fallback to1.0.0 or a Web-only upgrade. No installer policy expansion
is proposed here. Required release checks and public Console-overlay smoke remain
in [GO/NO-GO](release-go-no-go.md); workflow ordinary image smoke alone is insufficient
as operator Console acceptance. Failed post-push validation never permits explicit
RC tag overwrite; a future rc.2 needs its own source/version approval.

## Disabled-default and coordination availability

`Settings` defaults false/claim_only/insecure HTTP false with no Broker/socket/IPC/
keyring requirement while disabled. The ordinary image-only base passes no Console
activation/mounts; overlay defaults remain false and explicit activation requires
exact Origins/private bind/HTTP acknowledgement and authenticated retained-envelope
checks. Source review and existing default/disabled-page tests confirm hidden entry/
404s and normal auth/coordination behavior. Fresh, persisted, source/image-only and
installer regressions test coordination without Broker/keyring provisioning.
Only disposable synthetic fixtures opt into HTTP Console for testing; no operator
config or company service is changed by this review.

## Q1–Q83 review crosswalk

All83 owner decisions below are included once, retaining their chosen titles.
Evidence codes identify implemented paths and **related** isolated tests; they do
not assert83 unique complete tests or real production PASS. All actual operator
cases are unchecked in the separate checklist. R1 affects participant evidence;
real browser/remote topology and bounded emulator limitations are explicit.

- F: metadata/policy/quota/crypto, `backend/tests/test_console_foundation.py` and
  `test_console_migration_crypto.py`; `services/console/foundation.py`, credentials,
  targets and models/migration.
- G/T: `backend/tests/test_console_gateway.py`, Broker IPC/executor/SSH,
  `services/console/runtime.py`/websocket and `tests/console_mock/transport_check.py`
  plus gateway checks (real disposable SSH, no real BMC).
- U: `backend/tests/test_console_ui.py`, `scripts/console_browser_smoke.py`, local
  pinned xterm/addons, Console templates/modules and server-authorized APIs.
- D: `backend/tests/test_console_deployment.py`, `scripts/console_deployment_smoke.py`,
  Compose/entrypoint/network/custody/keyring tools. S: direct static source review.

| Decision | Confirmed title | Evidence path | Reviewed treatment / remaining gate |
| --- | --- | --- | --- |
| Q1 | Per-Client fixed SSH identity (A). | F, G/T | Actual per-Client fixed identities/topology: C3-01/02; multi-Client expansion separately approved. |
| Q2 | Manual SUT-to-tmux mapping (owner clarification). | F, U | RD mapping is separate from inventory; exact existing name/socket checked in C3-03/04. |
| Q3 | Direct BMC SSH RD-provided credentials (B). | F, G/T, U, D | BMC per-flow RAM only; BMC-02/03 and C4 plaintext hop approval pending. |
| Q4 | Mapping edit disconnects old Web terminals (D). | F, G/T, U | Scoped epochs/fencing/outbox; AUTH-04/07, no remote-process kill. |
| Q5 | No Lab CIDR allowlist for BMC IPv4 (A). | F, D | C2 retained: RFC1918/fixed22, no Lab allowlist; BMC-01/C4-05 actual inventory pending. |
| Q6 | RD may manage BMC host-key trust (C). | F, G/T, U | RD BMC trust retained; C5-01..05 independent comparison remains open. |
| Q7 | RD may manage Console Client host-key trust (B). | F, G/T, U | RD Client trust retained; Client-wide impact/revoke, C5 remains open. |
| Q8 | Both password and SSH key (C). | F, G/T, U, D | Password and encrypted-private-key paths; actual algorithm/account compatibility pending. |
| Q9 | Admin Web GUI credentials (A). | F, G/T, U, D | Admin replacement-only GUI; independent Broker KEK and Web RAM exposure reviewed. |
| Q10 | No terminal recording (A). | F, G/T, U, D | Canary/non-persistence evidence; no recording; OS/remote-side logging not controlled. |
| Q11 | Separate terminal page/tab (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q12 | No keyboard-idle cutoff (B). | G/T, U | No keyboard-idle cutoff; login/lease expiry still applies. Real output-only soak pending. |
| Q13 | Bounded auto reconnect (B). | G/T, U | Browser-close/HTTP-abort injection is UI evidence, separate real SSH failure tests; no replay. |
| Q14 | RD names and unique user count (B). | G/T, U | R1 OPEN: first participant assertion failed; rerun success is not root-cause resolution. |
| Q15 | Shared writable UART warning (B). | G/T, U | Shared writers/no writer lock retained; R1 and actual C3-05 evidence pending. |
| Q16 | Copy/paste and multiline confirmation (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q17 | In-tab output survives reconnect (B). | U | Same xterm/tab instance retained; remote ANSI/alternate-screen redraw can replace visible rows. No transcript guarantee; review actual reconnect-buffer behavior in C3-08/UI-02. |
| Q18 | On-demand connectivity checks only (A). | G/T, U | GET/save do not probe; explicit Client auth validation remains the Q70–72 exception. |
| Q19 | Failure UI actions (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q20 | Same-Lab binding only (A). | F, G/T, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q21 | Unique active Client/tmux pair (A). | F | A14 disabled-Client slots are provisional implementation choice; reenable collision refuses. |
| Q22 | Optional mapping change reason (B). | F, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q23 | All RD see Connection History (B). | F, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q24 | No restore button (A). | F, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q25 | Direct BMC SSH port fixed 22 (A). | F, G/T, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q26 | Unconfigured connections still visible (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q27 | Switch UART/BMC modes in same page (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q28 | Multi-tab concurrency (A). | G/T, U | Independent tabs/generation/slot checks; participant behavior also affected by R1. |
| Q29 | Per-user 10-session limit (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q30 | My Console Sessions list view only (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q31 | Fullscreen button (B). | U | Fullscreen succeeds in Chromium; unavailable API/browser fallback needs actual workstation acceptance. |
| Q32 | Adjustable font (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q33 | Do not persist font (A). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q34 | Basic in-terminal search (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q35 | 10,000-line scrollback (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q36 | Full connection status (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q37 | Background tabs continue (A). | G/T, U | Background output subject to browser sleep/resources; actual long-running observation pending. |
| Q38 | ANSI terminal (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q39 | TERM xterm-256color (A). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q40 | Native tmux size negotiation (A). | G/T, U | Native multi-client tmux size policy; custom socket/owner topology not repaired. |
| Q41 | Terminal-focused shortcuts (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q42 | SSH connect timeout 10 seconds (B). | G/T, D | 10s establishment bound, not an idle timeout; real BMC algorithm/latency pending. |
| Q43 | 3 BMC authentication attempts per flow (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q44 | No cross-flow failed-auth lockout (A). | G/T | No Gateway cross-flow lockout; remote account may enforce its own lockout. |
| Q45 | Focus terminal after success (A). | U | Foreground explicit writable focus; background/RO must not steal focus. |
| Q46 | Leave-page warning while live (B). | U | Handler requests cancellation; native OS/browser prompt is best-effort, not guaranteed. |
| Q47 | Disconnect immediately (A). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q48 | Basic Send Key (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q49 | Standard mouse behavior (A). | U | Maintained emulator behavior; actual browser/remote mouse reporting acceptance pending. |
| Q50 | Right-click paste (C). | U | Clipboard denial injected on localhost then native Ctrl+V; real LAN HTTP permissions pending. |
| Q51 | No Clear Screen button (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q52 | Reconnect button always visible (B). | G/T, U | Same logical slot/new attachment; no reuse of old ticket/input. |
| Q53 | Confirm reconnect if Connected (B). | U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q54 | Friendly diagnostic errors (B). | G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q55 | No standalone Test Connection (A). | F, G/T, D | No mapping-save SSH test; mandatory Admin candidate auth is not waived. |
| Q56 | Conditional save confirmation (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q57 | UART/BMC separate edit/save (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q58 | RD can clear mappings (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q59 | Disable/reactivate Client, no direct deletion (B). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q60 | Disabled Client not newly selectable (A). | F, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q61 | Only Admin modifies Client IP (A). | F, G/T, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q62 | Client SSH port admin-settable (A). | F, G/T | Client custom port1–65535 requires operator approved egress port; BMC remains22. |
| Q63 | Client IPv4 only (A). | F, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q64 | Required admin-defined Client name (A). | F | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q65 | Globally unique Client IPv4 (A). | F | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q66 | Optional Client notes (B). | F, U | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q67 | Admin may move Client across Labs after unbind (B). | F, U | Retained bindings must be manually unbound before Lab move; no silent clearing. |
| Q68 | Changing Client credentials disconnects users (B). | F, G/T, U, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q69 | Secrets non-viewable (A). | F, G/T, U, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q70 | Validate replacement credential before storing (B). | F, G/T, D | Pinned authentication-only before candidate commit; failure preserves old links/credential. |
| Q71 | Verify SSH on new Client before create (B). | F, G/T, D | No orphan enabled Client on failed initial trust/auth; creating Admin approves pin. |
| Q72 | Verify Client IP/port change before save (B). | F, G/T, D | Validate changed endpoint with trusted pin and current credential outside SQL write lock. |
| Q73 | Creating Admin approves initial Client host key (A). | F, G/T, U, D | Implemented path and related isolated assertions reviewed; applicable operator AUTH/UI/C3 cases remain pending. |
| Q74 | Client host-key update revokes all its UART Web sessions (B). | F, G/T, U, D | Client-wide UART revoke only after explicit reviewed trust commit; no auto reconnect. |
| Q75 | BMC host-key update revokes that SUT's BMC Web sessions (B). | F, G/T, U, D | SUT-specific BMC revoke only; UART remains unaffected. |
| Q76 | Maintenance/Out of Service does not inherently ban Console (B). | F, G/T, U | Maintenance flag independent of coordination restriction; not an implicit write grant. |
| Q77 | Admin temporary maintenance Console grant (B). | F, G/T, U | Named grant, no Claim/Queue/Reservation mutation; AUTH-05 actual acceptance pending. |
| Q78 | Grant durations up to 24 hours (B). | F, G/T, U | Presets1/2/4/8/12/24h, Normal permanently revokes; other rights recomputed. |
| Q79 | Grant reason optional (B). | F, U | Blank reason permitted, safe actor/target/expiry audit remains. |
| Q80 | No grant notifications (A). | F, G/T, U | No grant notices, email or Teams side effects. |
| Q81 | Multiple RD grants per SUT (A). | F, G/T, U | Several named RD grants remain independent; no writer lease. |
| Q82 | Extend active grant within original 24h (B). | F, G/T, U | Original created_at+24h ceiling, no silent clamping/renewal. |
| Q83 | Immediate fresh grant after expiry (A). | F, G/T, U | Fresh approval/new grant ID only; no automatic revival of expired link. |

## Actual verification for this review

These are current-source runs, not copied Phase E PASS claims.

| Check | Actual result |
| --- | --- |
| Full unit suite | **358 passed**,141.79s; one existing Starlette TestClient deprecation warning |
| Ruff check/format |PASS,99 Python files |
| Shell/JS module syntax, actionlint1.7.7 (application/release workflows), pip check |PASS |
| Existing baseline/Day2/Day3 Chromium |All three PASS |
| First actual mock SSH + Console browser runner |**FAIL** at participant assertion line375; R1 remains OPEN |
| Unchanged clean repeat of same mock SSH + Console browser runner |**34 Console checkpoints PASS**, original tmux sessions preserved; does not erase first failure |
| Console image-only deployment runner |**Seven groups PASS**: fresh, privilege/mount/IPC5088:80, raw-socket egress, old-main populated upgrade/cold restore, compatible old-image rollback, independent KEK recovery and missing-approval/Broker fail-closed |
| Source Docker/container Compose |PASS:5088→80, UID/cap/security boundary, migrations, deadlines, browser, persistence, cold restore |
| Ordinary image-only Compose/low-password leg |PASS with locally loaded image, no checkout/build in deployment directory; no registry pull claim |
| Installer lifecycle |PASS: actual containers fresh/rerun/backup upgrade/config-secret-admin-Lab preservation; mount preflight/registry selection/download are simulated by the existing runner, with failure contracts covered by unit tests |
| Default-off independent check |PASS: flags false/claim_only/false, Broker/IPC/keyring unset, runtime absent, health200; existing legacy/installer runs prove coordination workflows |
| Proposed version parser / public registry HEAD / remote Git tags |PASS read-only observations above; no image pull/signature/OCI proof from HEAD |
| Operator/hosted CI/public RC digest smoke |NOT RUN; RC does not exist, no company access or publication authorized |

Python3.12.14, Docker28.4.0, Compose2.40.3, Chromium `/usr/bin/chromium`,
OpenSSH9.2/OpenSSL3.0.22, tmux3.3a, AsyncSSH2.23.1. Isolated HTTP test fixtures
explicitly opt in only inside disposable containers; no live/site setting changed.
Browser-close/aborted-request and clipboard-denial injection remain synthetic UI
fault evidence, distinct from actual mock SSH lifecycle checks. Native browser
unload prompts, real LAN clipboard, long observation, real TLS/WSS/load and company
reboot/mount/firewall/Client/BMC are not certified. The deployment runner's old
image is pinned pre-Phase-E main00776f9 (already console001_b01), not the published
1.0.2 image. Populated pre-Console schema migration is unit-tested separately;
a public1.0.2-digest-to-RC container upgrade is not claimed. Operator DATA-04 must
use the actual intended prior image/schema on a disposable copy before live use.

Reproduction (locked dev virtualenv, supported local Docker; retain cloud proxy/CA):

```sh
pytest -q
ruff check backend scripts tests/console_mock
ruff format --check backend scripts tests/console_mock
bash -n setup.sh scripts/entrypoint.sh
for file in backend/app/static/console-*.js; do node --input-type=module --check < "$file"; done
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
docker build --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t sut-console001-c:local -t sut-console001-e:local .
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_CONSOLE_BROWSER=1 python scripts/console_mock_smoke.py
# Prior fixture image is built from exact00776f9 main, per Phase E reproduction/CI.
python scripts/console_deployment_smoke.py
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_SMOKE_EXPORT_IMAGE=sut-console001-rc:regression python scripts/container_smoke.py
SUT_SMOKE_IMAGE=sut-console001-rc:regression SUT_SMOKE_LOW_SECURITY=1 python scripts/container_smoke.py
SUT_INSTALLER_TEST_IMAGE=sut-console001-rc:regression python scripts/installer_smoke.py
```

Tests use private temporary synthetic directories/DBs and their own containers/
networks/volumes; normal runner cleanup completed. No real mount, production data,
credentials or real BMC/Client is used. Local candidate image ID
`sha256:21016265452e2cdae8619f65daba3bcc396ae7884fc8754c0b0a7670e3ef7690`;
source regression image ID
`sha256:cc3b3ff8e8db9371c4e0946a6ca226727308a6eb4d6b0fc31ec2b6112c596624`.
These are local build IDs, not published RC immutable manifests. Actual anonymous
published-digest pull/OCI/source/Console-overlay validation remains a future gate.

Static document validation:83 unique ordered decision rows,59 local links, shell
example syntax, owner-ledger immutability and vendor hashes PASS.

## Findings, blockers and corrective actions

| ID | Finding / impact | Status and next action |
| --- | --- | --- |
| R1 | First Console Chromium run failed at `scripts/console_browser_smoke.py:375`, two-distinct-RD participants after native detach/manual reconnect; last completed checkpoint was beforeunload. Clean unchanged rerun passed34. | **OPEN verification blocker for RC publication**. Capture only safe connection-state/generation/participant metadata on reproduction under comparable load. Determine harness reconnect synchronization vs runtime/session loss; add a focused regression and independently reviewed correction if needed. Do not claim a product defect/root cause proven, relax security leases or hide initial failure. |
| R2 | API metadata/README/historical design prose is not current image version or full production acceptance. | Non-runtime documentation/version-governance observation. Use inventory and this review as current status; no product version/UI redesign. |
| R3 | Existing installer excludes prerelease/paired Console upgrades; TLS/WSS rollout and actual C3/C4/C5 unverified. | Explicit operating boundary, not a reason to bypass parser/trust/HTTP guards. Use approved digest overlay; real pilot and future WSS require separate acceptance. |

No release-blocking application defect is conclusively demonstrated by current
passing unit/transport tests; R1 is a real observed failed acceptance assertion,
not dismissed by its rerun. No application/security/test assertion is modified in
this readiness PR. Independent review must resolve its release disposition.

## Delivery / release readiness

PENDING BRANCH PUSH AND ONE PR ATTEMPT. No Git release tag, image push/alias change,
company access/deployment, production DB write, insecure-mode activation or automatic
merge. Review preparation completion does not authorize RC publication or pilot.
