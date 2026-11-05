# Acceptance traceability and Phase B–E milestones

All cases below are **planned**, not implemented/executed Console tests. Phase A
validates documentation only; existing MVP checks are not evidence of live Console
security. Owner source: [complete83 decisions](../CONSOLE_001_REQUIREMENTS.md).
Baseline file SHA256: `5a5aabe43f7c83f5a99f1258fa1a7de395cae6ed53b42eb907b1132ef14ae856`.
Each row preserves the selected baseline title; the linked design documents supply
mechanisms, boundaries and unresolved gates. Read [architecture](architecture.md),
[schema](data-model.md), [security](security.md), [contracts](contracts.md) and
[compatibility](compatibility.md) together.

## Q1–Q83 matrix

| Decision | Planned phase | Required fixture / assertion (NOT YET RUN) |
| --- | --- | --- |
| Q1 — Per-Client fixed SSH identity (A). | C | Two Clients use different fixed identities; RD never supplies UART credential. |
| Q2 — Manual SUT-to-tmux mapping (owner clarification). | B/C | RD chooses registered Client + manually enters existing tmux; no session inventory prerequisite; invalid name rejected. |
| Q3 — Direct BMC SSH RD-provided credentials (B). | C/D | Every BMC authentication prompts; canary username/password absent from SQLite/log/audit/browser storage after success/failure/disconnect. |
| Q4 — Mapping edit disconnects old Web terminals (D). | C | Commit UART/BMC remap while typing; affected old WS/SSH fenced/closed, no auto-reconnect or remote tmux/PuTTY termination. |
| Q5 — No Lab CIDR allowlist for BMC IPv4 (A). | B/C/E | No Lab CIDR allowlist; strict IPv4 and undisputed sensitive-target denial; public-class cases remain blocked pending C2 resolution. |
| Q6 — RD may manage BMC host-key trust (C). | C/D | RD compares BMC old/new fingerprint OOB before auth; wrong/unapproved key receives zero credentials; audit safe replacement. |
| Q7 — RD may manage Console Client host-key trust (B). | C/D | RD Client trust acceptance warns shared scope, checks OOB and invalidates affected UART only. |
| Q8 — Both password and SSH key (C). | B/C | Password/key Clients coexist; encrypted keys/passphrases and password methods validate without fallback. |
| Q9 — Admin Web GUI credentials (A). | B/C/D | Both Admin roles provision encrypted Client secrets; RD forbidden; no plaintext DB or secret reveal. |
| Q10 — No terminal recording (A). | B/C/D | Seed unique terminal/clipboard canaries; no transcript, video, recording/download route, DB/log/APM/body retention. |
| Q11 — Separate terminal page/tab (B). | D | Open Console from SUT Detail into separate large page/tab, not embedded terminal. |
| Q12 — No keyboard-idle cutoff (B). | C/D | No keyboard events while output continues; connection remains; real login expiry still fences it. |
| Q13 — Bounded auto reconnect (B). | C/D | Finite backoff, auth/epochs/key rechecked; BMC re-prompts, no input replay, no retry on revocation. |
| Q14 — RD names and unique user count (B). | C/D | Two tabs same RD + another RD yield distinct count2, optional total3 and RO/RW labels; no external PuTTY enumeration. |
| Q15 — Shared writable UART warning (B). | C/D | Two simultaneous UART writers both reach same existing tmux; visible Shared Console and names; no writer lease/latest-typist tracking. |
| Q16 — Copy/paste and multiline confirmation (B). | C/D | CRLF, lone CR/LF, hidden controls and multiline paste require preview/count approval; cancel/RO sends zero bytes. |
| Q17 — In-tab output survives reconnect (B). | D | Transient reconnect preserves RAM scrollback/boundary; refresh loses it; storage/network logs contain no transcript. |
| Q18 — On-demand connectivity checks only (A). | C/D | Opening page, listing and sweeps cause zero SSH/ICMP/tmux probes; Connect alone probes; live heartbeat permitted. |
| Q19 — Failure UI actions (B). | D | Timeout/absent tmux/bad fixed credential offer Retry/Edit or contact Admin, never scan alternate hosts. |
| Q20 — Same-Lab binding only (A). | B/C | Same-Lab validation for both roles and raw/concurrent DB writes; Client/SUT incompatible move rejected. |
| Q21 — Unique active Client/tmux pair (A). | B | Concurrent active duplicate Client/tmux creation yields one success; distinct Clients allow same name; archived/disabled slots free; conflicting restore fails safely. |
| Q22 — Optional mapping change reason (B). | B/D | Blank mapping reason accepted; actor/time/safe old/new values always recorded. |
| Q23 — All RD see Connection History (B). | B/D | All active RD can read paginated connection history including archive; inactive/anonymous denied; no secret. |
| Q24 — No restore button (A). | D | No history restore button/API; manual edit to old values still validates/records/revokes. |
| Q25 — Direct BMC SSH port fixed 22 (A). | B/C | BMC port override payload rejected; all BMC sockets22; Client configurable port independent. |
| Q26 — Unconfigured connections still visible (B). | D | Enabled feature shows both Not Configured modes and Edit to authorized viewer, zero SSH before Connect; feature off hides/disables all terminal entry. |
| Q27 — Switch UART/BMC modes in same page (B). | C/D | Mode switch closes only own current attachment; new mode waits explicit Connect and BMC reauthentication. |
| Q28 — Multi-tab concurrency (A). | B/C/D | Same RD across SUTs/modes/tabs independent; close one leaves others unless explicit endpoint-wide revocation. |
| Q29 — Per-user 10-session limit (B). | B/C | Race11 connects; at most10 reserved/active slots; reconnect same slot; stale close cannot free replacement; dead peer cleanup. |
| Q30 — My Console Sessions list view only (B). | B/D | My Console Sessions shows own N/10 and details only; cannot enumerate/kill another user's or own other tab's sessions. |
| Q31 — Fullscreen button (B). | D | Fullscreen/Esc/fallback fit and PTY resize, no disconnect. |
| Q32 — Adjustable font (B). | D | Font starts14, steps1 within10–24, dimensions refit; no hidden preference. |
| Q33 — Do not persist font (A). | D | Reload/new page resets14; no local/session storage or user-profile font field. |
| Q34 — Basic in-terminal search (B). | D | Terminal-focused Ctrl+F, case-insensitive previous/next/highlight over retained RAM, no regex/remote input/saved search. |
| Q35 — 10,000-line scrollback (B). | C/D | More than10k lines trim oldest, extreme long line bounded in bytes, slow output backpressure never unbounded memory. |
| Q36 — Full connection status (B). | D | All six public lifecycle statuses and failure reason render; input only Connected; no RTT widget. |
| Q37 — Background tabs continue (A). | C/D | Background tab receives logs within browser limits; sleep reconnect preserves policy, no guarantee of missed output. |
| Q38 — ANSI terminal (B). | C/D | Maintained xterm ANSI cursor/colors/interactive tools/basic keys; hostile escape/link/OSC52 fixtures safe. |
| Q39 — TERM xterm-256color (A). | C | Every gateway PTY requests xterm-256color; no picker or remote settings rewrite. |
| Q40 — Native tmux size negotiation (A). | C/D | Different simultaneous sizes propagate native PTY/tmux sizing, no120x40 or window-policy mutation; independent BMC resize. |
| Q41 — Terminal-focused shortcuts (B). | C/D | Focused Ctrl+C/D/Z/arrows/Tab/Enter pass once; Ctrl+F local; RO blocks all input including emulator/mouse responses; browser shortcuts remain browser-owned. |
| Q42 — SSH connect timeout 10 seconds (B). | C | Fake TCP/KEX/auth stall reaches fixed10s establishment timeout, not keyboard-idle timeout; no alternate host. |
| Q43 — 3 BMC authentication attempts per flow (B). | B/C/D | Three explicit BMC attempts/flow; fourth denied; password cleared each attempt; Client fixed credential fails once/contact Admin. |
| Q44 — No cross-flow failed-auth lockout (A). | B/C | New flow allowed after prior failures without rolling lockout; concurrent auth bounded and audited, no brute-force auto retry. |
| Q45 — Focus terminal after success (A). | D | First writable success focuses terminal; background reconnect and RO do not steal focus. |
| Q46 — Leave-page warning while live (B). | D | Connected/Reconnecting beforeunload best effort; cancel preserves link; absent browser prompt is documented limitation. |
| Q47 — Disconnect immediately (A). | C/D | Disconnect immediate and idempotent, correct counter, no reconnect/remote kill; output stays in tab. |
| Q48 — Basic Send Key (B). | C/D | Each Esc/Tab/Ctrl+C/D/Z Send Key once, disabled outside writable Connected; no advanced hardware key. |
| Q49 — Standard mouse behavior (A). | C/D | Native selection/copy/scroll/mouse reporting; no extra Mouse Mode toggle, RO selection without input. |
| Q50 — Right-click paste (C). | D | User-triggered right-click clipboard; denied/insecure API falls back Ctrl+V; multiline confirmation and RO/disconnect denial. |
| Q51 — No Clear Screen button (B). | D | No Clear Screen control/API; normal terminal behavior retains approved memory limits. |
| Q52 — Reconnect button always visible (B). | C/D | Reconnect always visible, disabled mid-connect; old attachment torn down first, same quota slot, no input duplication. |
| Q53 — Confirm reconnect if Connected (B). | D | Connected manual reconnect confirms; cancel untouched; Failed/Disconnected no confirmation; tmux survives. |
| Q54 — Friendly diagnostic errors (B). | C/D | Sanitized stable errors/suggestions and audit reason, never stack/secret/raw SSH stderr; same behavior both transports. |
| Q55 — No standalone Test Connection (A). | B/C | Mapping save never probes; no standalone Test Connection; Admin create/credential/IP/port validation still mandatory. |
| Q56 — Conditional save confirmation (B). | B/C/D | Zero-session save direct; new or generation-changed affected session invalidates preview even with same counts; CAS409, fresh Confirm & Save. |
| Q57 — UART/BMC separate edit/save (B). | B/C | Independent revisions/Save for UART and BMC, change one closes only its affected transport. |
| Q58 — RD can clear mappings (B). | B/C/D | RD clears one mapping to Not Configured, records history and scoped revoke without deleting SUT/Client/tmux. |
| Q59 — Disable/reactivate Client, no direct deletion (B). | B/C/D | Admin disables bound Client, retains mapping/history, denies new UART and revokes existing; no DELETE; reviewed reenable path. |
| Q60 — Disabled Client not newly selectable (A). | B/D | Disabled Client absent from new selections, retained existing binding visible; backend rejects selecting disabled even forged API. |
| Q61 — Only Admin modifies Client IP (A). | B/C | RD cannot change Client IP; Admin preview/validation/commit retains ID/bindings and invalidates UART only after success. |
| Q62 — Client SSH port admin-settable (A). | B/C | Admin Client port22 default and1..65535; invalid/unauthorized denied, success revalidates/revokes; BMC fixed22. |
| Q63 — Client IPv4 only (A). | B/C | Client accepts strict IPv4 only; DNS/IPv6/alternate numeric encodings fail without lookup. |
| Q64 — Required admin-defined Client name (A). | B | Required trimmed/casefold Client name unique per Lab under concurrent insert/update, cross-Lab reuse allowed. |
| Q65 — Globally unique Client IPv4 (A). | B | IPv4 uniqueness across Labs/disabled Clients/different ports enforced at DB and friendly409. |
| Q66 — Optional Client notes (B). | B/C/D | Optional visible notes with safe audit; notes-only save makes zero probes/revocations, no secret in examples. |
| Q67 — Admin may move Client across Labs after unbind (B). | B | Move bound Client fails listing all incompatible retained bindings; manual unbind then move retains identity/secret/history and destination name rule. |
| Q68 — Changing Client credentials disconnects users (B). | B/C/D | Confirmed validated credential replacement closes all Client UART, not BMC/external sessions; failed test retains old generation and live links. |
| Q69 — Secrets non-viewable (A). | B/C/D | Even Super Admin GET/export/error cannot reveal existing private key/password/cipher; replacement-only form/configured state. |
| Q70 — Validate replacement credential before storing (B). | B/C | Known pinned key plus successful auth required before credential commit; fake server asserts zero shell/PTY/exec/tmux, failures leave old state. |
| Q71 — Verify SSH on new Client before create (B). | B/C | Failed new Client host trust/auth or uniqueness race leaves no Client/credential row; creating Admin approves pin first; failure audit secret-free. |
| Q72 — Verify Client IP/port change before save (B). | B/C | New IP/port candidate tested against exact pin with old credential outside write lock; failed/stale evidence preserves old address and links. |
| Q73 — Creating Admin approves initial Client host key (A). | B/C/D | Creating Admin explicit OOB initial Client key comparison; RD cannot create Client via trust API. |
| Q74 — Client host-key update revokes all its UART Web sessions (B). | B/C | RD Client key update shows old/new and SUT/RD/session impact; audit/CAS + revoke all that Client UART, no auto retry/remote kill. |
| Q75 — BMC host-key update revokes that SUT's BMC Web sessions (B). | B/C | RD BMC key update shows impact, audit/CAS + revoke that SUT BMC only, UART/PuTTY remain. |
| Q76 — Maintenance/Out of Service does not inherently ban Console (B). | B/C/D | Maintenance/OOS by itself neither denies Console nor grants writes; three policies and operational warning independent of Claim/Queue/Reservation restrictions. |
| Q77 — Admin temporary maintenance Console grant (B). | B/C | Admin named Maintenance/OOS grant supplies RW without Claim; other user/SUT unaffected; no usage/booking/queue mutation. |
| Q78 — Grant durations up to 24 hours (B). | B/C | Creation presets1/2/4/8/12/24, boundary expiry, Normal transition permanently revokes; close if no alternate right. |
| Q79 — Grant reason optional (B). | B | Optional blank reason accepted; admin/RD/SUT/timestamps/expiry always audited safely. |
| Q80 — No grant notifications (A). | B/C/D | Grant create/revoke/expiry emits no in-app/email/Teams message; own page can show effective expiry and live unauthorized link closes. |
| Q81 — Multiple RD grants per SUT (A). | B/C | Several RD independent grants/expiries and shared writes; concurrent duplicate same RD/SUT prevented; revoking one leaves others. |
| Q82 — Extend active grant within original 24h (B). | B/C | Extend only active before expiry, created_at immutable, <=original+24h; old/new expiry audited, continuously valid links stay; invalid bounds rejected. |
| Q83 — Immediate fresh grant after expiry (A). | B/C | New distinct approved grant immediately after expiry, no cooldown/automatic renewal; old audit retained, closed old session never auto-reconnects. |

## Cross-cutting matrix beyond numbered Qs

| ID | Acceptance gate |
| --- | --- |
| X1 | Feature false by default, claim_only default, HTTP opt-in false; strict true/false and exact three enum values, invalid startup denied; recreate rather than rebuild to change approved settings. |
| X2 | Full three-policy Cartesian matrix for all roles/current Claim/booking-only/queue-only/no Claim, active/inactive/password-change/expired/logout/reset states, both Labs/transports and maintenance grants. Reservation readiness is never a Claim; input/output-only sessions both lose expired authority. |
| X3 | Handshake foreign/null/forged Origin, scheme/port mismatch, cookie without ticket, ticket without login, wrong user/tab/SUT/transport/generation, replay/expiry, CSRF and query-secret attempts all rejected. Existing signed cookie is not an immutable WS authorization. |
| X4 | SQL locks never held during SSH/IPC auth; instrument async/thread boundaries and assert gate ordering, rollback, validation evidence expiry and broker death before/after commit. Recovery outbox closes exactly affected sessions; precommit bytes cannot be recalled. |
| X5 | Secret root separated from session key/DB backup; swap ciphertext/AAD, wrong/missing key, interrupted rewrap, encrypted private key/passphrase handling, canary nonlogging and empty-directory backup recovery all tested synthetically. |
| X6 | Target deny tests cover all local host/container aliases, metadata/cloud endpoints, loopback/link-local/multicast/broadcast/reserved, disguised IPv4/IPv6/DNS and prohibited protocol/forwarding/exec fields. Public-class interpretation C2 unresolved, not an accepted hidden allowlist. |
| X7 | HTTP/WS allowed only explicit opt-in with transport warning and LAN rules; approved HTTP clipboard fallback. HTTPS/WSS through trusted proxy, forged forwarded headers, no downgrade, CSP same-origin and secret nonlogging tested independently. |
| X8 | Existing pytest/Ruff/three Chromium/container/image-only/backup-restore/installer regression gates remain green with Console off and synthetic Console on; approved Demo UI and reservation deadlines do not change. No real host/credentials in CI. |

## Fixtures and evidence design

- Temporary migrated SQLite: two fictional Labs, each with multiple Clients; one
  Client with one UART and one with several existing tmux targets; independent BMC
  mappings; three roles, disabled/must-change users, multiple claims and grants.
  Use documentation-only IPv4 fixtures for schema tests, never route them to real
  devices. Network-classifier unit tests do not connect even when classifying IPs.
- Deterministic clocks at exact login/grant/ticket/lease expiry,24h extension bound
  and restart. No host clock modification. Race barriers for new connections during
  preview/validation/commit, duplicate maps/IPs/names,11 connects, expiry vs extension,
  stale attachment closes and session/account/Claim changes while typing.
- Fake SSH adapter/server with synthetic host keys/credentials, scripted timeout,
  changed fingerprint, failed authentication, absent tmux, invalid exec, resize,
  high-volume/hostile ANSI. CI asserts command logs only permit declared lookup/
  attach, or zero exec for pre-save authentication. No real Client/BMC commands.
- Remote isolation fixture for C1 must demonstrate prefix/session-switch/run-shell/
  socket/escape rejection without altering a representative persistent tmux/minicom
  setup. A mock which always says 'safe' is insufficient for the production gate;
  use an explicitly approved disposable topology before any real pilot.
- Chromium tests for every Q UI action, two simultaneous writers/RO viewer, duplicate
  tabs, fullscreen/focus/unload, clipboard grant/deny and opted-in insecure context,
  reload/RAM storage loss, >10k lines, CSP/escape attacks, transport states and errors.
- Collect commands, exact test counts, screenshots, sanitized status-only audit,
  SQLite counts/integrity/FKs and mock SSH traces **without terminal/clipboard or
  authentication payloads**. Never commit actual credentials, DBs or private setup.

## Milestones and exit gates (not implementation claims)

| Phase | Implementation scope | Required exit evidence |
| --- | --- | --- |
| A (this PR) | Architecture, schema plan, threat model, contracts,83-row traceability, scope amendment/review register | Documentation checks and owner review; no code/migration/UI/deployment/live network work. Open risks remain visible. |
| B | Additive schema + strict config OFF, short auth/transaction service boundaries, crypto interfaces with synthetic keyring, mappings/history/Client/grant CRUD validation behind feature flag; broker/SSH mocked | Review Phase A/A3/A4/A8 first. Fresh/populated migration preservation, uniqueness/FK/races/quota/grant bounds, permission/CSRF/secret projection, encryption/rotation/restore unit integration, existing off-mode suite. All new behavior tested without real SSH. No 'Client validation passed' fake production endpoint. |
| C | Pinned SSH broker/UDS protocol, auth-only Client validation, tickets/WS auth, leases/fencing/outbox, BMC attempts and scoped revocations, constrained UART adapter | Resolve C1/C2/C3, algorithm compatibility and trust process. Mock-server + authorized disposable remote containment proof; TOCTOU/crash/revocation/read-only/10-session/timeout tests; no generic shell/forwarding or real infrastructure access without separate approval. |
| D | Standalone xterm UI, SUT Detail entry/history/edit, Admin Client management, own sessions/grants, participant warnings, all approved controls | Q11–19/26–54 Chromium matrix, font/search/clipboard/ANSI/resize/input RO and high-output budgets, secret/storage/log canaries, approved existing UI and all legacy regression gates. No transcript or additional writer lock. |
| E | Reviewed opt-in Compose/broker/key mounts/egress documentation, image-only deploy, independent key backup/recovery/rotation, operator training and staged pilot | Feature remains off initially. Synthetic fresh/populated container and install-upgrade/recovery + trusted HTTP/WS and HTTPS/WSS tests. Explicit operator/owner/security approval, production topology and risk signoff before live pilot, separately authorized release. |

B may build complete mockable interfaces while C blockers are tracked, but must not
ship placeholder successful SSH validations or enable a connector. B–E are separate
reviewed PRs, each updates evidence/TASKS only after tests actually pass. Phase A
completion is documentation delivery, not approval of the design, migration, pilot
or entire Console feature.

## Production gates and rollback

1. Review scope amendment and explicitly resolve C1–C5 for intended topology. Verify
   out-of-band host fingerprint source, dedicated restricted identities and tmux
   ownership/socket constraints. Never repair a remote tmux/minicom daemon silently.
2. Approve broker privilege/egress/self-deny design and actual HTTP risk acceptance,
   bind/firewall/boot mount ordering, dependency/security budgets and key custodians.
   Confirm valid config and feature-off deny behavior on the intended image.
3. Back up SQLite cold with matching image/config and independent keyring; rehearse
   new empty-directory restore and wrong-key fail-closed behavior. Verify record
   counts, schema head, existing accounts/usage/history/queue/reservation integrity.
4. Run required tests on isolated synthetic fixtures and an explicitly authorized
   disposable representative tmux topology. No production-derived credentials or
   inventory in CI/screenshots/repo. Mark every absent environment check unverified.
5. Separate approved live pilot, bounded Lab/SUT scope, explicit three-policy choice,
   HTTP opt-in and key provisioning by operator; do not turn all_authenticated on
   implicitly. Monitor metadata-only audit and verify scoped revocation while
   preserving remote sessions/external access. No automatic Docker publication.
6. Rollback first disables Console and fences all links/tickets without changing
   existing Claim/Queue/Reservation. Keep new SQLite/keys for reconciliation. If
   reverting schema/image, restore matching pre-upgrade DB/config/keyring into an
   empty directory and use compatible image. No blind downgrade or overlaid WAL.
   Never destroy an independent key needed for retained backups.
