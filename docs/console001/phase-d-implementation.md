# CONSOLE-001 Phase D — Web Console UI and administration

Status: implemented and locally verified against disposable mocks; results belong
in [verification](phase-d-verification.md). Base main `0ad530a` contains merged
A/B/C; branch `feature/console001-phase-d`. Q1–Q83 and C1/C2 remain unchanged.
This separate owner request authorizes Phase D only; production/Phase E/release
remain independently gated and Console stays OFF in operator configuration.

## Frontend and permission boundaries

- Standalone `/suts/{id}/console`, opened from Detail in a new tab with noopener;
  UART/BMC share one terminal page. GET never probes SSH. Terminal page authorization
  uses the existing three-policy predicate; `/suts/{id}/connections` independently
  permits every active/password-changed RD to edit mappings and read history.
- `/console/sessions` lists only current user's sessions; `/admin/console-clients`
  and `/admin/console-grants` require Lab/Super Admin. No RD inventory/user-management
  route or other-tab kill capability is introduced.
- Templates reuse existing Bootstrap/Jinja layout and authenticated same-origin
  JSON APIs. Names, errors, history and terminal-adjacent content use textContent
  or Jinja escaping. Shared dialogs require explicit confirmation, with an unchecked
  independent fingerprint-verification acknowledgement for Host Keys.

## Local pinned assets

xterm6.0.0, Fit0.11.0, Search0.16.0 and noble/hashes2.4.0 are pinned in
`frontend/console/package.json`/lock. `vendor.mjs` copies reviewed UMD assets/licenses
and bundles only the SHA256 implementation for browsers (esbuild0.28.2). SHA256
works on opted-in LAN HTTP without relying on secure-context WebCrypto.subtle.
`static/vendor/console/PROVENANCE.json` records local file SHA256 hashes. No CDN,
Node/npm installation or source build occurs at application runtime. Prettier is
an exact development-only formatter; node_modules is excluded from Git/builds.

The maintained Search addon uses the pinned xterm decoration API; allowProposedApi
is enabled for that API and tested against the matched versions. No custom terminal
parser/theme replaces xterm. OSC52 and OSC8 are consumed, links cannot activate,
and no clipboard-write/download/image/web-links addon is loaded. Text selection,
copy, scrolling, terminal keys and native mouse reports remain xterm behavior;
all text/binary emulator-generated input passes the same writable/Connected gate.

xterm's renderer generates inline styles. **Only the standalone terminal response**
allows inline CSS; script-src stays self-only, without unsafe-inline/unsafe-eval,
connect-src self, frame/object denial and no-referrer/no-store. Other app pages
retain their original CSP. This scoped CSS exception needs review alongside future
TLS/WS rollout; it is not a global scripting exception.

## Lifecycle, input and memory

Current tab owns an in-memory random tab ID, ticket, generation and monotonic input
sequence. Ticket is first WS frame, never URL/storage. Six lifecycle states drive
controls. Backend SSH retries remain authoritative; browser socket retries are
bounded, use the existing same-logical-session attach contract and never replay
input. Closed/stale/revoked attachment stops automatic retry and needs explicit
Connect; explicit reconnect may obtain a fresh reservation if old metadata closed.
No new remote-exec or unreviewed WebSocket frame type is added.

Mode switch and Disconnect close only this tab, clear authentication/paste state,
and require explicit new Connect. Connected manual Reconnect confirms first;
current xterm instance and its bounded RAM scrollback remain, with an in-terminal
divider and a persistent external reconnect notice. Remote ANSI/tmux alternate-screen
redraw can replace visible rows; this is a terminal emulator, not a transcript.
Each explicit foreground writable connection focuses terminal; background updates do not steal focus. Best-effort
beforeunload covers Connected/Reconnecting; reload loses terminal/font state.

Terminal font14px, integer10–24; fullscreen/Esc/resize use Fit and bounded2..500
columns/1..200 rows with110ms debounce. Scrollback10,000 lines. Browser pending
render writes are capped1MiB and fail closed on pressure. No terminal content,
clipboard, search, font or credentials go to SQLite/logs/LocalStorage/sessionStorage/
IndexedDB. Existing notification cursor storage remains separate and contains no
Console data. Python/JavaScript GC cannot promise forensic memory zeroization.

Paste uses Phase C paste_begin/paste_chunk only: <=64KiB, SHA256, <=8KiB chunks,
paced to respect frame budget, no replay queue. CR/LF/CRLF are counted; multiline
requires explicit preview/confirmation. NUL and hidden Cc/Cf controls are rejected
rather than silently normalized. Preview is bounded and discloses truncation.
Right-click uses Clipboard API only on gesture; denied/insecure context explains
Ctrl+V/native paste fallback. Read-only/disconnected input/paste/Send Key is disabled
locally and independently enforced by the unchanged Gateway/Broker.

## Mapping, Client, trust and grants

UART/BMC settings independently preview/save/clear with expected revision, optional
reason and exact impacted-session confirmation. Same-Lab enabled Client choices
exclude disabled new selections; retained disabled mapping remains visible. History
is paginated/read-only, with no restore action and no SSH test on mapping Save.

Client form chooses metadata-only PATCH for name/notes/unbound Lab move. New Client,
endpoint/identity or replacement credential uses actual client-validations, explicit
initial/candidate Host Key acknowledgement, validation_id and impact preview before
commit. Secrets are replacement-only and inputs cleared on each submit/result;
transient candidate variables are discarded on success/failure/cancel. Existing
secret never appears in GET/form/response. Enable/disable uses the existing metadata
PATCH/preview, not fictitious separate endpoints from the old design proposal.

Host Key UI shows target/IP/port, algorithm, exact SHA256/new and old fingerprint,
OOB instructions and affected SUT/RD/session counts. Connect explicitly discovers
key; an already identical trusted pin is reused, unknown/changed pin always needs
human acknowledgement. Standalone review is a deliberate trust operation with
existing backend scope/audit/revocation, never an automatic trust acceptance.

Maintenance UI chooses named eligible RD/SUT, fixed1/2/4/8/12/24h presets, optional
reason, explicit extension to original creation+N hours (never >24h), confirmed
revoke and independent grant rows. Revoke confirmation is a Phase D engineering
UX choice under the owner's instruction, not a newly numbered Q84 decision.
No grant notifications or coordination mutations are added.

## Backend UI projection compatibility

Phase C routes/payloads were inspected directly. Added read-only Admin
`/api/v1/console/admin/grants` and `/admin/grant-options` expose only safe grant
metadata and eligible RD display_name/team/ID plus Maintenance/OOS SUTs. This avoids
giving Lab Admin Super Admin account administration. Existing `/sessions/me` now
adds own SUT/Lab name and connected_at, and truthful Broker availability. No schema
migration, SSH forwarding/command API or terminal protocol extension is required.

## Remaining rollout boundaries

Verification uses disposable mock OpenSSH/tmux/BMC plus the actual Broker/Gateway.
Only synthetic HTTP UI is loopback-published for host Chromium; SSH stays on the
internal mock network, Broker uses private IPC and separate KEK/DB mounts. No
company host/production SQLite/real credentials/tmux was touched or image published.
Operator Compose/setup/release configuration remains unchanged. C3 actual account/
default-socket topology, shared shell privileges, C4 plaintext interception risk,
C5 trustworthy OOB fingerprints, trusted TLS/WSS, key recovery/rotation and real
load/production acceptance remain Phase E gates; no production readiness claim.
