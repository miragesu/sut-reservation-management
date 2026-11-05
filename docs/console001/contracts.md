> **Phase C executable subset:** see [current DTOs/routes and deviations](phase-c-implementation.md#gateway-contracts) and [verification](phase-c-verification.md). Proposed descriptions below remain the historical design baseline; full terminal UI is Phase D.

> **Phase B implementation note:** the [mock-only foundation report](phase-b-implementation.md) and [verification](phase-b-verification.md) record the actual implemented subset and provisional choices. The design/proposed assertions below remain the Phase A baseline; do not read “planned” as deployed or mark the full Q-matrix/terminal gates complete. Live validation/SSH/WS/Broker remain unavailable.

# Proposed HTTP and WebSocket contracts

Design only; no routes or handlers exist yet. Schemas below are versioned proposals,
subject to [review assumptions](compatibility.md). Shared service authorization and
[transaction/fencing sequence](architecture.md) apply to **every** entry point.

## Common rules

REST prefix `/api/v1/console`. Active server-side login and completed mandatory
password change required. Mutations require existing CSRF token and exact Origin
validation for secret/trust/ticket operations. Never accept actor IDs/roles from
payload. Extra fields forbidden. UTC ISO8601 with offset at boundaries; display
Taipei. JSON validation errors name fields without reflecting submitted values.
Responses no-store; forms never prepopulate stored password/key. SSH protocols
must not be exposed through arbitrary URL, port-forward, command or socket APIs.

Proposed JSON errors preserve the existing envelope:
`{"detail":{"code":"mapping_conflict","message":"Connection changed; review again.","request_id":"opaque","retryable":false}}`.
401 invalid session;403 role/policy/Origin/CSRF;404 missing/disabled feature;409 stale
revision, duplicate slot or confirmation required;422 syntax/target/grant bounds;
429 concurrent resource/quota limit (not password lockout);503 broker unavailable.
Safe codes include `client_disabled`, `not_configured`, `quota_exceeded`,
`host_key_unknown`, `host_key_changed`, `trust_challenge_expired`,
`target_denied`, `target_policy_unresolved`, `credential_auth_failed`,
`tmux_not_found`, `ssh_timeout`, `grant_expired`, `session_revoked`.
No raw stderr/banner/traceback/terminal bytes or remote BMC username in errors.

## Routes and payloads

| Method / relative route | Principal and input / response |
| --- | --- |
| GET `/clients` | All active RD; paginated enabled choices with id/name/IP/port/Lab/notes/configured trust; retained disabled Client visible in its existing binding. Admin include_disabled listing. No credentials/ciphertext. |
| POST `/client-validations` | Admin; create/update operation, expected Client metadata/connection revisions, candidate IPv4/port/username/auth_method and replacement secret when applicable. Does on-demand host discovery/auth-only test; yields RAM-only validation_id or trust challenge. No persistent Client on failure. |
| POST `/clients` | Admin; validated safe metadata + single-use validation_id bound to exact candidate and initial Admin trust acceptance. Commit only after current uniqueness/auth checks.201 returns nonsecret Client state. |
| PATCH `/clients/{id}` | Admin; expected_version, changed fields, validation_id for host/port/credential changes, confirmation_id if impacted links. Notes/name-only do not probe or disconnect. Return new metadata/connection revisions and revocation delivery state. |
| POST `/clients/{id}/enabled` | Admin; enabled Boolean, expected_version, impact confirmation when disabling affected sessions. Retain mappings/history. Reenable checks active-slot invariants, no standalone background SSH test. |
| POST `/clients/{id}/move-lab` | Admin; Lab and expected_version; refuse incompatible retained bindings, list IDs for manual unbind. No automatic clearing. |
| GET `/suts/{id}/connections` | Active RD; UART and BMC separately, configured/disabled state, revisions, safe fingerprint, capability for current policy, operational reason. No live reachability check. |
| POST `/suts/{id}/uart/preview` | Active RD; expected_revision, desired Client/tmux or explicit clear=true, optional reason. Returns impact and confirmation_id if needed; never SSH probe. |
| PUT `/suts/{id}/uart` | Active RD; same payload + confirmation_id if required. Syntax/Lab/active uniqueness/CAS rechecked. Clear resets to Not Configured; only UART revoked. |
| POST `/suts/{id}/bmc/preview` | Active RD; expected_revision, IPv4 or clear=true, optional reason. Same independent confirmation rules. No port/username/password accepted. |
| PUT `/suts/{id}/bmc` | Active RD; corresponding independent save. BMC-only invalidation; reset endpoint trust on remap. |
| GET `/suts/{id}/history` | Active RD, including retained archive history; paginated safe mapping events only, no restore action. |
| POST `/trust/challenges` | Active RD for existing endpoint, Admin for draft Client; explicit on-demand discovery with endpoint/draft ID and revision. Return public algorithm/key SHA256/old pin/impact/challenge expiry; never send credential. |
| POST `/trust/accept` | Same role; challenge_id, expected_trust_revision, exact observed fingerprint, out_of_band_verified=true, impact confirmation. Initial Client creation is Admin-only. This Boolean is user attestation, not proof of an independent source. Changed trust uses fresh preview/version and scoped revocation. |
| POST `/suts/{id}/grants` | Admin; user_id, duration_hours enum1/2/4/8/12/24, optional reason. Target Maintenance/OOS, active RD, no effective duplicate. Does not alter Claim or issue notifications. |
| PATCH `/grants/{id}` | Admin; expected_revision,new_expires_at, optional reason. Active and not expired, strictly extends, <=original created_at+24h. UI uses explicit presets; no silent cap or renewal. |
| POST `/grants/{id}/revoke` | Admin; expected_revision, optional reason. UX confirmation is unconfirmed engineering A1/Q84; re-evaluate every affected session's other rights. |
| GET `/suts/{id}/my-grant` | Own effective grant/expiry only, no in-app notification side effects. |
| GET `/sessions/me` | Own sessions only, paginated SUT/Lab/transport/status/connected_at and usage N/10, Console detail link. No another-tab kill endpoint. |
| POST `/sessions` | Policy-authorized current user; SUT, UART/BMC, expected endpoint revision, per-tab random instance ID. Reserve quota, create auth flow/ticket. No credential in response or URL. |
| POST `/sessions/{id}/attach` | Same owner/login/tab; logical-session reconnect ticket, expected attachment generation and intent. Reuse slot, never duplicate active attachment. Explicit Connect needed after revocation. |

Read-only existing configuration/history/mapping authority is independent of Claim.
Console page GET `/suts/{id}/console` requires policy read capability, but can render
Not Configured modes without an SSH attempt; nonholders in claim_only use separate
SUT Detail mapping/history routes instead of unauthorized terminal access. No hidden
UI permission bypass: the same checks run in ticket and WS input paths.

No standalone Test Connection endpoint/button exists. `client-validations` is a
mandatory Admin transaction stage for Q70–Q72, not a general RD probe tool. Server
RAM validation state has proposed2min expiry and is bound to candidate hash,
actor/login/current host/credential versions and observed key. Commit consumes it;
expired/stale proof returns409 and requires a fresh explicit validation. For new
Client, encryption may prepare an opaque pending bundle in RAM but stores no
Client/credential row until auth and final transaction succeed.

Preview response example (no real addresses/secrets):

```json
{"expected_revision":7,"affected":{"sut_count":2,"rd_count":3,"session_count":4},"confirmation_id":"opaque-single-use","expires_at":"2026-11-05T12:00:00Z","requires_confirmation":true}
```

Confirmation binds exact session IDs and attachment generations, not just counts,
operation before/after digest, resource revisions, actor/login and expiry. A new
session with the same count or reconnect generation invalidates it. With zero
sessions Save can skip preview, but final recheck can return `confirmation_required`.
Key acceptance always requires deliberate fingerprint comparison even with no links.
No response can reveal an existing Client password/private key, even to Super Admin.

## WebSocket handshake and framing

Endpoint `/ws/console/v1/sessions/{opaque_session_id}` has **no query credential or
ticket**. Subprotocol fixed `sut-console.v1`, not a bearer secret. Browser carries
normal session cookie and exact Origin. Before accept, validate origin/session/
feature/transport and a small global handshake budget; first frame must carry the
one-use ticket within proposed3s, otherwise close with no terminal output/metadata.
A quota reservation expires after30s if never attached. Ticket itself expires30s.
Initial ticket creation is CSRF-protected POST; an Origin or cookie alone is not
sufficient. No tokens in Referer, path, access logs or browser storage.

Client first text frame:

```json
{"v":1,"type":"hello","ticket":"ephemeral-one-use","tab_id":"opaque","attachment_generation":1,"cols":100,"rows":30}
```

Ticket atomically binds login digest, user, SUT/transport, mapping/Client/credential/
trust epochs, tab and Origin. Recheck live state on redemption; the header does not
create a forever-authorized WS connection. Deny stale generation/replay; no echo
of ticket. Actor IDs, destinations, tmux commands and permissions are never frame
parameters supplied by browser.

| Direction / type | Contract |
| --- | --- |
| server `state` | state enum, safe reason_code, retryable, effective mode, current generation; no RTT field |
| server `auth_required` | BMC only after host trust, flow_id and remaining attempts. Password entry user-driven, never automatic replay. |
| client `authenticate` | BMC flow_id, username/password; secret frame in RAM only, no logging/persistence. Counter increments before auth I/O; simultaneous retry CAS denied. Max3/flow, purge each attempt, do not send secrets into the PTY. |
| server `connected` | transport, RO/RW, connected_at, effective grant expiry if any; no Client credential or BMC username |
| client `input` | current attachment_generation, monotonic per-generation seq and base64 bytes; writable Connected only. All key/paste/mouse/emulator-generated bytes pass the same policy/epoch gate. Not a remote command API. |
| client `paste_begin` / `paste_chunk` | Bounded paste ID + generation + expected byte hash/count and explicit multiline approval, followed by bounded chunks. At most64KiB RAM assembled; actual CR/LF/control counts/hash checked before any SSH write. Cancel/expiry clears it. A single line needs no extra user prompt. |
| client `send_key` | seq plus enum esc/tab/ctrl_c/ctrl_d/ctrl_z, same Connected/RW gate; maps to one known control sequence, no arbitrary command. |
| server `input_ack` | seq and stage=broker_written only; means local write, not remote execution. Duplicate/out-of-order seq rejected, no replay on absent ACK. |
| server binary | PTY output bytes for current generation; browser renders streaming UTF8 with standard xterm parser. No output acknowledged as durable or recorded. |
| client `resize` | integer cols/rows, proposed2..500 /1..200 and debounce100ms; propagate PTY size. Do not force120x40 or remote tmux window settings. |
| server `participants` | target-scope distinct Web RD display names/modes/count; optional total sessions, no other users' private session IDs or external PuTTY claims |
| client `disconnect` | immediate own current WS/SSH teardown, no confirmation; no remote process kill |
| server `revoked` | safe scoped reason and manual_connect_required=true; drop pending input, close. Never auto-reconnect. |
| ping/pong | server-driven protocol liveness, not keyboard idle; no browser storage or transcript |

Manual Reconnect from Connected first confirms in UI, then closes only its current
attachment and obtains a new bound attach ticket. Disconnected/Failed require no
confirmation. Do not carry terminal input frames to a new generation; no input ACK
scheme promising exactly-once remote command execution. WebSocket/TCP delivery is
not proof that a remote shell executed a command. Failed writes produce a boundary
notice, not replay. BMC reconnect waits for new credentials if authentication needed.

Close codes proposed:1000 intentional/normal,1008 authorization/Origin/revocation,
1009 oversized frame,1011 internal/broker failure,1013 overload/backpressure.
Do not place sensitive data in close reason (bounded safe enum). Policy close is
nonretryable even if the browser would otherwise retry network failures.

## Secret input bounds (engineering proposal)

External Client/BMC SSH passwords are not application account passwords: do not
apply MINIMUM_PASSWORD_LENGTH or LOW_SECURITY_PASSWD to an existing remote identity.
Propose nonempty exact username/password, no silent trimming/composition rewrite,
username256 UTF8 bytes/password1024 bytes, HTTP admin payload128KiB and private
key64KiB decoded; review SSH-library limits in B/C. Remote password/key material
never enters audit/SQL request logging. Admin validation does not consume a Web
Console quota slot because it is not a terminal; it still shares bounded concurrent
SSH-auth resource budgets and cannot become a background scanner.

## Browser terminal controls and budgets (engineering assumptions)

Use locally vendored/pinned xterm.js, fit and search addons. ANSI colors/cursor/
interactive keys, TERM=xterm-256color; no custom terminal parser/theme.10,000 lines
per-tab scrollback; no LocalStorage/IndexedDB/sessionStorage transcript, preference
or credential. Reconnect retains RAM buffer and inserts a boundary; reload loses
it. Background tabs remain connected without keyboard-idle timeout.

Default font14px; A+/A− integer10..24 step1 and fullscreen/Esc feed fit/PTY resize;
no font persistence. Focus writable terminal on first successful connection only,
not a background reconnect. Ctrl+F searches case-insensitively in RAM with next/
previous/highlight, no regex/server queries. No Clear Screen button. Esc/Tab/Ctrl+C/
D/Z Send Key each sends once when writable Connected. Preserve normal selection,
scroll and native remote mouse reporting; read-only permits selection, not mouse
input that would reach the remote program. Ctrl+W/T remain browser-reserved.

Single-line paste goes directly after Connected/RW validation. Normalize CRLF for
line counting, detect lone CR/LF as multiline, show line count+safe preview and
require explicit approval before sending any of it. Other control characters get
an escaped preview and warning; never treat ESC, NUL or hidden newline as a safe
single-line bypass. Cancel sends zero bytes. Proposed reject NUL and over-budget
paste rather than truncate silently. Q41 ordinary focused controls still pass as
controls; paste safeguards do not turn Ctrl+C into text. Right-click requests
clipboard only on user gesture; Ctrl+V/native paste fallback when HTTP browser APIs
deny permission. Never log preview/clipboard; RO rejects paste at server too.

Proposed budgets: text control frame16KiB; input chunk8KiB decoded; total confirmed
paste64KiB split into bounded chunks without storing it for replay; broker/gateway
output queue1MiB/session and browser10k lines plus byte cap16MiB for extreme long
lines. Maximum inbound32KiB/s/session with bounded burst; pause SSH reading on
backpressure, disconnect slow consumers rather than unbounded memory growth. Excess
paste/input rejected clearly, no silent duplicate/truncation. Search/highlight
operates within retained bounded data. Validate base64 before allocating; binary
client frames unsupported. A hostile remote cannot trigger OSC52, downloads or
unsafe link handlers. A malicious writer can type the same bytes directly; a paste confirmation flag is a
UX safeguard, not proof that arbitrary input came from a keyboard. No clipboard
text or preview is ever audited.

These limits must be load-tested in D and are not owner
business decisions or an idle cutoff.

## Private gateway ↔ broker RPC

Propose length-prefixed `console-broker.v1` messages with request/session ID,
attachment generation, broker/web boot IDs and monotonically ordered control seq,
authenticated over the private Unix socket. No public broker endpoint or generic
shell/exec/forward request. Messages: `probe_key`, `validate_client`,
`encrypt_candidate`, `candidate_commit_or_discard`, `open`, `input`, `resize`,
`fence`, `close`, `lease_refresh`, `rewrap`. Each has bounded typed fields; candidate
handles bind actor/login/proposal/trust/version and expire. Broker independently
checks target restrictions, exact key, current generation/mode/fence and lease
NotAfter before network or byte delivery. Untrusted JSON cannot override these.

Existing encrypted Client envelope/credential ref goes to broker; no decrypted
existing credential returns to gateway. New candidate secret transiently crosses
web parsing/UDS but never RPC logs. `open` is exact endpoint/transport only, with
pinned key and authorization proof, not an arbitrary address accepted from browser.
Output RPC tags session/generation; gateway drops stale output after a remap and
browser ignores callbacks from an old WebSocket object/generation on reconnect.
No terminal bytes are written to SQLite/outbox/audit.

Fence ACK means no new broker-queued bytes for that scope reach SSH; prior delivered
bytes cannot be undone. Failure before ACK rejects mutation before commit and
retains old state. Commit creates durable revocations; postcommit close is retried
idempotently, and old frozen generations cannot resume after broker loss. Startup
reconciliation and short independent leases close orphan attachments before new
admission. This proposed RPC has not been implemented or fuzz/load-tested.
