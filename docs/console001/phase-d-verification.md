# CONSOLE-001 Phase D verification — 2026-11-05

**Local acceptance: PASS against disposable mocks. Production readiness: NOT CLAIMED.**
Base main `0ad530a1dc1b4dc8b7843d4cc958084078461aee`; branch
`feature/console001-phase-d`. [Implementation](phase-d-implementation.md).
No owner Q1–Q83/C1/C2 changes, new migrations, operator configuration changes,
production access, release tags or Docker publication. Alembic head remains
`console001_b01`. Phase E requires separate review and authorization.

## Executed checks

| Check | Actual result |
| --- | --- |
| Existing baseline pytest | 337 passed |
| Final full pytest | **346 passed**, 129.57s; one existing TestClient deprecation warning; nine new HTML/authorization/vendor cases included |
| Ruff / module syntax / Prettier / pip dependency consistency | PASS |
| Locked npm install and local asset regeneration | PASS; xterm6.0.0/Fit0.11.0/Search0.16.0/noble hashes2.4.0; package lock, licenses and file SHA256 manifest committed |
| Three retained Chromium suites | PASS: baseline auth/dashboard/polling; Day2 coordination/calendar/history; Day3 modals/mobile/notification fallback |
| Console real Broker/SSH/PTY/tmux suite | PASS: existing Phase C transport, fencing/revocation, Broker restart, two-layer RO and session preservation |
| New Console Chromium | **34 named checkpoints PASS**, listed below; final application rerun passed |
| Docker source build | PASS; local image ID `sha256:ed5506d33a9b9ca1a20d601b384bc8cc72a21db1de5675defef811575d3aa624`, tag `sut-console001-d:final`; not a published registry digest |
| Source Compose/container regression | PASS: 5088→80, UID10001, zero capabilities, no-new-privileges, non-root low port, migration, deadlines, browser, persistence, cold recovery |
| Image-only Compose | PASS with locally loaded `sut-console001-d:regression`, source-free directory, no build; low-password-mode leg included; no registry pull claim |
| Installer lifecycle | PASS: actual fresh/rerun/low-mode bootstrap/cold-backup upgrade, persistent secret/config/admin/Lab, health/migrations/5088:80/bind integrity, no secret output |
| Hosted GitHub CI / production LAN / public image pull | NOT RUN in this change; local CI-equivalent checks do not imply remote success |

Reproduction (Python3.12.14 virtualenv with locked backend requirements and installed
Playwright; Chromium executable `/usr/bin/chromium`; local Docker28.4.0):

```bash
python -m pytest -q backend/tests
ruff check backend scripts tests/console_mock
for file in backend/app/static/console-*.js; do node --input-type=module --check < "$file"; done
(cd frontend/console && npm ci --ignore-scripts && npm run vendor)
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
# Use only a disposable local daemon. Cloud builds retain proxy/CA trust.
docker build --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt -t sut-console001-c:local .
SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt SUT_CONSOLE_BROWSER=1 python scripts/console_mock_smoke.py
# Source build/Compose exports a local image, then image-only and installer tests reuse it.
SUT_SMOKE_EXPORT_IMAGE=sut-console001-d:regression python scripts/container_smoke.py
SUT_SMOKE_IMAGE=sut-console001-d:regression SUT_SMOKE_LOW_SECURITY=1 python scripts/container_smoke.py
SUT_INSTALLER_TEST_IMAGE=sut-console001-d:regression python scripts/installer_smoke.py
```

Consult runner docstrings for environment controls. All databases/directories,
Docker networks/volumes and credentials are synthetic and cleaned by the runners.
No real server, UART hardware, BMC address, company SQLite or production secret
is used. Console test flags are set only inside the disposable fixture.

## Topology and evidence boundary

The fixture creates OpenSSH9.2/OpenSSL3.0.22, tmux3.3a and AsyncSSH2.23.1,
with pre-existing mock sessions and raw synthetic UART output. Actual web UID10001
communicates via authenticated UDS with Broker UID10002; Broker owns KEK/SSH and
has no database. The SSH endpoint is on an internal Docker network. The UI leg
alone publishes a random **127.0.0.1** port from a bridge-network web container,
so host Chromium can use real HTTP/WebSocket; no public SSH/host networking.

Random login, SSH password, private key and passphrase are generated per run,
passed through private fixture stdin and never placed in source, argv, browser
storage or reports. The runner suppresses credential-adjacent exception details;
failures report a harness line and last completed checkpoint. Database canary
exclusion, SQLite integrity/FKs and five coordination-table counts are asserted.
Existing tmux sessions remain and the missing-session case creates none.

Browser-close/backoff proof intentionally dispatches a browser close event and
aborts two attach HTTP requests in the test context; it proves finite UI retries,
not WAN fault tolerance. The separate Phase C runner exercises real SSH transport
failures/restarts. Clipboard denial is injected on localhost to reproduce LAN
HTTP/permission failure; native Ctrl+V is subsequently exercised. beforeunload
handler cancellation is asserted; an OS-native browser confirmation prompt cannot
be guaranteed. These are explicit test boundaries, not skipped production gates.

## Chromium checkpoint matrix

| # | Actual PASS checkpoint |
| --- | --- |
| 1 | Admin initial host-key acknowledgement and auth-before-create, secret field cleared |
| 2 | Admin metadata editing without credential reveal |
| 3 | RD-compatible independent mapping save/history; no inventory privilege shortcut |
| 4 | Real UART WebSocket/tmux read-write and explicit plaintext warning |
| 5 | Font controls and case-insensitive local previous/next Ctrl+F search |
| 6 | Fullscreen / Esc and fit observer |
| 7 | Bounded single/multiline CRLF paste, confirmation cancel and hidden-control rejection |
| 8 | Right-click clipboard denial provides Ctrl+V fallback |
| 9 | Native Ctrl+V paste works after right-click Clipboard API denial |
| 10 | UI simulated browser-close and aborted attach requests use finite backoff and same-slot ticket generations |
| 11 | Connected Reconnect confirmation/cancel, retained RAM buffer and divider |
| 12 | BMC host-key trust, exact remaining attempts, cleared password and fresh reconnect prompt |
| 13 | Mode switch back to UART requires and completes explicit Connect |
| 14 | All five Send Key controls send once while writable |
| 15 | Font bounds 10–24, integer steps and fit/resize |
| 16 | ANSI rendering and hostile OSC52 / OSC8 output cannot write clipboard or create links |
| 17 | More than 10,000 output lines trims old scrollback; search covers retained RAM only |
| 18 | Native tmux detach remains ordinary SSH account shell; TERM xterm-256color |
| 19 | Connected beforeunload warning handler requests cancellation (native prompt remains browser-controlled) |
| 20 | Nonholder read-only terminal, disabled input/paste/keys, separate RD mapping permission and shared warning |
| 21 | Claim-authorized RD reconnect becomes writable; two concurrent authorized UART writers |
| 22 | Same-RD duplicate tabs count once as participant, twice in own session inventory without remote kill |
| 23 | Ten real multi-tab sessions allowed, 11th rejected, own Disconnect preserves peers |
| 24 | Release revalidation downgrades nonholder UX immediately without input replay |
| 25 | Failed credential replacement preserves old live connection and clears submitted secret |
| 26 | Bound Client Lab move refusal and validated encrypted-private-key rotation with affected-session revocation |
| 27 | Lab Admin named independent maintenance grants, bounded extension and confirmed scoped revoke |
| 28 | Independent mapping clear/impact cancel/confirm/history and stale-update handling |
| 29 | Changed Client/BMC Host Keys show independent old/new fingerprints, require acknowledgement, and revoke only their transport |
| 30 | Reload drops RAM buffer/font preference; credentials and terminal canaries absent from browser storage / IndexedDB |
| 31 | Sensitive Client/BMC/terminal canaries absent from synthetic SQLite, integrity/FKs intact |
| 32 | Missing existing tmux gives Failed / Retry / Edit, no automatic creation or retry; corrected mapping reconnects |
| 33 | Unbound Lab move preserves Client; same-Lab choices, retained disabled mapping and reenable with existing credentials |
| 34 | Detail configuration summaries and separate noopener tab; both missing mappings stay Not Configured |

## Corrections verified during development

Pinned Search requires the xterm decoration API; matched versions now enable it.
Native Ctrl+V now reaches the guarded paste event instead of sending xterm's SYN
control. Dialog submit/cancel resolves synchronously, preventing a deferred close
from cancelling the next confirmation. Paste scrolls to current output after search;
fullscreen exit suppresses stray Escape. Client load/validation disables the form
to prevent replacement-credential races. Explicit foreground writable connections
focus terminal; automatic/background updates do not steal focus. A further repeat exposed tmux repaint overwriting the in-terminal reconnect
divider; a persistent external reconnect notice now accompanies the terminal
divider, and the browser assertion targets that stable notice. Remote ANSI remains
free to repaint the screen; no transcript guarantee is made. The final full
Console runner passed all 34 checkpoints after this correction. No required case is marked xfail/skipped.

## Remaining review / production gates

- Review scoped terminal-only inline CSS CSP exception required by xterm; scripts
  remain self-only and other pages retain CSP.
- HTTP/WS is explicitly opted in only for the mock. Actual LAN operator acknowledgement,
  plaintext credentials/terminal risk, network ACLs, real browser permissions and
  HTTPS/WSS deployment are not certified here.
- Fixed shared SSH identities expose the account's ordinary Linux shell after
  native detach; no per-SUT OS confinement or individual remote-shell attribution
  is claimed. No tmux/minicom creation/termination is added by the Gateway.
- Actual Console Clients, physical UART/minicom, custom tmux socket permissions,
  real BMC implementations, production performance/HA and production recovery
  require separate Phase E acceptance with approved infrastructure.
- App non-persistence tests do not guarantee forensic RAM erasure, extension,
  operating-system clipboard, browser password-manager or screen-capture control.
- No screenshots containing secrets or terminal transcripts are committed; the
  reproducible assertions and named checkpoint output are the test evidence.
- No company host, public image publication, deployment or automatic merge.

## GitHub delivery

Pending final branch push and one PR creation attempt. The branch targets `main`;
Phase E is not started by this PR. Exact delivery outcome will be recorded below.
