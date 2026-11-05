# CONSOLE-001 — Remote Debug Web Console Requirements Baseline

> Status: OWNER DECISIONS CAPTURED / DESIGN NOT YET APPROVED / IMPLEMENTATION NOT STARTED.
> Source: owner-confirmed Q1–Q83 in project discussion, plus confirmed topology, Compose access-policy and HTTP intranet exception. This document is the durable requirement input for Codex; it is NOT an assertion that these features are implemented.
> No production credentials, private BMC addresses, employee data, or SSH secrets belong in this public repository.

## 0. Objective and scope

Add an independent browser-based debug terminal to the existing FastAPI/Jinja2/Bootstrap SUT Reservation and Queue Management System. Preserve existing reservation, claim/release, queue, user, notification and history behavior. This is a NEW explicitly approved feature, not a retroactive change to the preexisting coordination-only MVP. No BMC power operations or automatic firmware commands.

Two Labs; each Lab has multiple Console Clients; each Console Client may manage one or many USB UART connections to SUTs. SUTs may use UART and/or direct BMC SSH. Lab Admin and Super Admin manage Console Client infrastructure; all active authenticated RD users can maintain individual SUT connection mappings. Both pathways share the same standalone browser terminal UI.

## 1. Canonical Q1–Q83 decision ledger

Each line records the selected answer and its material acceptance consequences. Earlier unselected alternatives must NOT be silently substituted.

### Q1–Q10: Connection, identity, security and logging

1. **Q1 — Per-Client fixed SSH identity (A).** Each Console Client has independently configured SSH username/credential managed by Lab Admin or Super Admin. RD does not enter Console Client credentials when opening UART.
2. **Q2 — Manual SUT-to-tmux mapping (owner clarification).** Active RD can choose an already registered Console Client and enter the pre-existing tmux session name for a particular SUT. They do not need a prepopulated list of all sessions; backend must validate the name. Console Client host IP itself remains an admin-owned record (see Q61).
3. **Q3 — Direct BMC SSH RD-provided credentials (B).** Ask for username and password for each direct BMC SSH connect; do not persist them in SQLite, browser storage, audit or logs. Discard after attempt/disconnect; re-prompt for later authentication.
4. **Q4 — Mapping edit disconnects old Web terminals (D).** Successful endpoint mapping change invalidates all affected active WebSocket/SSH sessions so no one silently continues typing into the wrong SUT. New connection uses updated mapping. Never kill remote tmux or minicom or external PuTTY sessions.
5. **Q5 — No Lab CIDR allowlist for BMC IPv4 (A).** **C2 clarification approved 2026-11-05:** Active RD may set any syntactically valid **RFC1918 private IPv4** address (10/8, 172.16/12, 192.168/16) without a per-Lab CIDR allowlist. Public/unicast non-RFC1918 IPv4 is not permitted for BMC endpoints. Block loopback, link-local, metadata, gateway/host/container self-addresses, broadcast and other sensitive destinations even when they appear within an otherwise private range; preserve gateway egress/SSRF controls. This narrows the original Q5 wording by explicit later owner decision and does not change RD self-service mapping permission.
6. **Q6 — RD may manage BMC host-key trust (C).** Show unknown or changed SSH host-key fingerprint, require deliberate comparison against a trusted source before credential transmission, permit active RD to accept/update, audit previous/new fingerprints. Never auto-disable host verification.
7. **Q7 — RD may manage Console Client host-key trust (B).** Active RD may similarly confirm/update Console Client SSH fingerprint, with higher-impact warning, trusted out-of-band comparison, audit, credential withholding until trusted, and session invalidation per Q74.
8. **Q8 — Both password and SSH key (C).** Each Console Client independently uses a fixed password or private-key credential configured by admin; support mixed deployments, prefer keys when available.
9. **Q9 — Admin Web GUI credentials (A).** Lab Admin/Super Admin manage Console Client usernames/passwords/key provisioning using Web GUI; protect secrets server-side with independent encryption/root key. Never echo existing credentials or store plaintext in SQLite.
10. **Q10 — No terminal recording (A).** No persistent terminal keystrokes, output, video or recording/download facility. Audit connection and mapping events only. RD may copy screen text. Existing remote-side logging is out of scope.

### Q11–Q20: Terminal lifecycle, collaboration and Lab boundary

11. **Q11 — Separate terminal page/tab (B).** Open Console from SUT Detail into a standalone, generously sized browser page/new tab; not embedded into the SUT Detail page.
12. **Q12 — No keyboard-idle cutoff (B).** While tab and network are alive and authorization/session valid, continue receiving logs without keyboard activity. Browser close, logout, user disable, auth expiry and explicit revocations still close sessions.
13. **Q13 — Bounded auto reconnect (B).** On transient failures, finite retry with backoff then manual Reconnect. Recheck auth, mapping and host key each attempt. Never replay unacknowledged terminal input. Direct BMC requires password reentry if re-authentication needed. No auto retry after policy/mapping/key revocation.
14. **Q14 — RD names and unique user count (B).** Show connected Web Gateway RD display names and distinct RD count; optionally also total sessions. Deduplicate same RD across tabs. Distinguish read-only and writer modes. No claim to enumerate direct PuTTY users.
15. **Q15 — Shared writable UART warning (B).** All authorized writers may type concurrently into same tmux session; no exclusive writer lease/takeover. When 2+ Web RD participate, show prominent Shared Console notice and names/count; don't track latest typist.
16. **Q16 — Copy/paste and multiline confirmation (B).** Single-line paste direct; multi-line paste requires count/preview confirmation. Reject paste for read-only users. Never log clipboard contents. Treat embedded CR/LF and control characters safely.
17. **Q17 — In-tab output survives reconnect (B).** Retain terminal scrollback across transient disconnect/reconnect, annotate boundary; reload/close loses content. No Local Storage, IndexedDB, server logs or database persistence; no promise to reconstruct missed remote output.
18. **Q18 — On-demand connectivity checks only (A).** No SSH/ICMP/tmux background monitoring. Show Not Connected until user attempts Connect. Validate Client SSH and existing tmux or direct BMC SSH only on explicit connection; live sessions may heartbeat.
19. **Q19 — Failure UI actions (B).** Clear error + Retry + Edit Connection. For bad Console Client fixed credential instruct contact admin; nonexistent tmux prompts mapping correction. Do not probe alternate clients automatically.
20. **Q20 — Same-Lab binding only (A).** SUT may link only to Console Clients in its own Lab; no cross-Lab exception for RD or admins. Server enforces invariants when SUT/Client lab changes.

### Q21–Q30: Mapping integrity and browser session inventory

21. **Q21 — Unique active Client/tmux pair (A).** One (Console Client ID, tmux session name) may map to at most one active SUT UART endpoint. Detect conflict and identify existing SUT; enforce at DB transaction level for concurrency. Same session name on different clients is OK. Archived/disabled bindings should not permanently occupy active slot.
22. **Q22 — Optional mapping change reason (B).** RD may leave reason blank. Always audit actor, time, old/new values; never audit credentials.
23. **Q23 — All RD see Connection History (B).** SUT Detail read-only history shows mapping changes, actors, timestamps, before/after and optional reason; retain with archived SUT; no secrets.
24. **Q24 — No restore button (A).** History is informational only; RD must manually edit mapping to old values through normal validation, history and revocation.
25. **Q25 — Direct BMC SSH port fixed 22 (A).** RD and admins cannot customize it in UI/API; Console Client SSH ports remain separately configurable.
26. **Q26 — Unconfigured connections still visible (B).** Console page exposes UART/BMC modes as Not Configured with Edit Connection shortcut. Never attempt SSH until configured and Connect clicked; feature hidden/disabled globally when Console disabled.
27. **Q27 — Switch UART/BMC modes in same page (B).** Switch detaches/closes current browser-side connection then presents other mode; user explicitly clicks Connect. Never kill tmux/minicom, retain Q3 reauthentication.
28. **Q28 — Multi-tab concurrency (A).** One RD may open several UART/BMC sessions for same SUT or across SUTs. Each tab independent, shared UART tmux permitted; closing one does not affect others except deliberate endpoint-wide revocations.
29. **Q29 — Per-user 10-session limit (B).** Maximum 10 concurrent active Web Console sessions across UART/BMC and tabs, fixed (not Compose-configurable); deny 11th. Race-safe allocation, eventual cleanup of lost tabs, reconnect must not consume another slot.
30. **Q30 — My Console Sessions list view only (B).** Show own SUT, Lab, transport, connected time/status, usage N/10 and detail link. No remote kill/terminate of other tabs; own current Console Disconnect is allowed; do not expose another RD's private sessions.

### Q31–Q40: Display controls and terminal behavior

31. **Q31 — Fullscreen button (B).** Enter/exit terminal fullscreen; Esc leaves. Resize PTY appropriately, no disconnect. Graceful fallback if browser API unavailable.
32. **Q32 — Adjustable font (B).** A+/A−, default 14px, integer 10–24px step 1; adjust PTY rows/columns on sizing; per-tab only.
33. **Q33 — Do not persist font (A).** Fresh/refresh page defaults to 14px, no local storage or user-profile font preference.
34. **Q34 — Basic in-terminal search (B).** Ctrl+F when terminal focused, case-insensitive text match, previous/next/highlight. Search current in-memory scrollback only; no regex, no saved queries, no remote input.
35. **Q35 — 10,000-line scrollback (B).** Per browser terminal, trim oldest lines beyond 10,000. Support Q17/Q34, no permanent recording; bounded buffering/backpressure for high-throughput logs.
36. **Q36 — Full connection status (B).** Not Connected, Connecting, Connected, Reconnecting, Disconnected, Failed, plus retry and understandable failure reason. Disable input when not Connected; no RTT/latency widget.
37. **Q37 — Background tabs continue (A).** A nonforeground tab stays connected and receives output as browser permits, subject to auth expiry, 10k scrollback and bounded resources. Browser sleep may cause lost output; reconnect per Q13.
38. **Q38 — ANSI terminal (B).** Standard ANSI colors, cursor movement/control, interactive tools and basic key sequences using maintained emulator e.g. xterm.js; no custom theme/parser.
39. **Q39 — TERM xterm-256color (A).** Request xterm-256color for Web SSH PTY/tmux attach; no user TERM picker and do not change remote tmux/minicom settings.
40. **Q40 — Native tmux size negotiation (A).** Do not fix UART terminal to 120x40 or override tmux window-size policy; browser resize propagates PTY changes. Accept native multi-client sizing/crop behavior. Direct SSH independently resizes.

### Q41–Q50: Keyboard, clipboard and reconnection

41. **Q41 — Terminal-focused shortcuts (B).** Ctrl+C/D/Z, arrows, Tab, Enter etc pass as terminal controls while focused; Ctrl+F triggers in-terminal search; browser-reserved shortcuts such as Ctrl+W/T need not be intercepted. Enforce read-only at server regardless of UI.
42. **Q42 — SSH connect timeout 10 seconds (B).** Fixed timeout for UART Console Client and direct BMC SSH establish stage, not an idle limit. On timeout show error and Retry/Edit; do not try alternative targets.
43. **Q43 — 3 BMC authentication attempts per flow (B).** RD can retry new username/password up to three times in one direct BMC connect flow. Purge password after each attempt. Console Client fixed credential failures fail immediately and refer to admin.
44. **Q44 — No cross-flow failed-auth lockout (A).** Do not add rolling-window failed password account lockout beyond Q43. No automatic brute-force retries; retain failure audit and cap concurrent in-flight auth attempts. Remote BMC policy may independently lock accounts.
45. **Q45 — Focus terminal after success (A).** Auto-focus connected writable terminal on first successful connect. Don't steal focus from other tabs/apps on background reconnect or enable input for read-only viewers.
46. **Q46 — Leave-page warning while live (B).** Best-effort browser beforeunload prompt only for Connected/Reconnecting on close/refresh. Browsers may suppress/customize. Cancel leaves session untouched.
47. **Q47 — Disconnect immediately (A).** Explicit Disconnect has no extra confirmation; release only this browser WebSocket/SSH, detach remote tmux without kill, preserve in-tab output and correct session counters. Do not auto-reconnect deliberate disconnect.
48. **Q48 — Basic Send Key (B).** Esc, Tab, Ctrl+C, Ctrl+D, Ctrl+Z; only on Connected writable terminal. Each click sends once, no replay or Ctrl+Alt+Del advanced hardware control.
49. **Q49 — Standard mouse behavior (A).** Select/copy text, scroll history, standard xterm.js mouse reporting when remote application enables it; no additional Mouse Mode control, read-only selection allowed.
50. **Q50 — Right-click paste (C).** Right-click terminal attempts immediate clipboard paste; single line direct, multiline requires Q16 confirmation. Honor browser Clipboard API/permissions and offer Ctrl+V fallback; cannot bypass browser security; forbid paste when disconnected/read-only.

### Q51–Q60: UI operations, mapping and Client lifecycle

51. **Q51 — No Clear Screen button (B).** Do not implement extra local clear action; shell/terminal standard behavior is sufficient, and retained scrollback/search rules remain.
52. **Q52 — Reconnect button always visible (B).** Even Connected can manually reconnect. Tear down only current browser SSH attachment/session then create fresh one, validate mapping/rights/host key, do not resend commands or duplicate session quota. Disable while Connecting/Reconnecting.
53. **Q53 — Confirm reconnect if Connected (B).** Connected requires confirmation before manual reconnect; Disconnected/Failed reconnect without confirmation. Cancel leaves active link. UART remote tmux remains alive.
54. **Q54 — Friendly diagnostic errors (B).** User-oriented failure reason and suggestion, no raw stack traces/secrets; consistent for UART/SSH and auditable; Retry/Edit as Q19.
55. **Q55 — No standalone Test Connection (A).** Save mapping without SSH reachability probe; Connect performs live check. Validate syntax, Lab and uniqueness at save. This does NOT waive mandatory SSH authentication testing for Console Client admin create/credential/IP changes (Q70–Q72).
56. **Q56 — Conditional save confirmation (B).** If editing would affect active sessions, show affected SUT/RD/session counts and ask Confirm & Save; otherwise save directly. Recheck optimistic mapping version and affected sessions atomically before applying; then revoke impacted Web links.
57. **Q57 — UART/BMC separate edit/save (B).** Independently persist UART Client+tmux mapping and direct BMC IPv4. Change one disconnects only that transport's affected Web sessions, not the other.
58. **Q58 — RD can clear mappings (B).** RD may clear UART or BMC connection individually to Not Configured. Respect Q56 confirmation, Q4 revocation and history. Never delete SUT, remote tmux/minicom or Client.
59. **Q59 — Disable/reactivate Client, no direct deletion (B).** Lab/Super Admin can disable Client even when SUT-bound. Deny new UART connects, revoke existing affected Web sessions, retain mappings and history; no hard delete; reenabling permits normal verification/reconnect.
60. **Q60 — Disabled Client not newly selectable (A).** Exclude disabled Client from new/reassignment choices; existing SUT bindings remain visible as Client Disabled. RD can clear or reassign to enabled Client; backend enforces.

### Q61–Q70: Client network, inventory and credentials

61. **Q61 — Only Admin modifies Client IP (A).** Lab/Super Admin edit Client IPv4, retaining Client ID and SUT associations. Show impacted sessions and confirm before valid update, revoke affected UART Web sessions, reverify host identity. RD only chooses Client record.
62. **Q62 — Client SSH port admin-settable (A).** Default 22 but valid 1–65535; only Lab/Super Admin may edit. On change validate and disconnect affected UART Web links. Direct BMC port remains fixed 22.
63. **Q63 — Client IPv4 only (A).** Do not support DNS hostnames/FQDN/IPv6 for Console Client connection target in this version.
64. **Q64 — Required admin-defined Client name (A).** Within each Lab names are case-insensitively unique; across Labs repeats allowed. RD sees name and IP; admin manages name, audited without breaking ID bindings.
65. **Q65 — Globally unique Client IPv4 (A).** No two Client records, including Disabled or across Labs, may use same IPv4, even if SSH port differs. DB uniqueness and clear collision error.
66. **Q66 — Optional Client notes (B).** Admin edits optional location/USB hub/maintenance notes visible to RD; no secrets. Notes-only edit should not disconnect Web links; audit it.
67. **Q67 — Admin may move Client across Labs after unbind (B).** Refuse Lab change while incompatible SUT UART bindings exist; list bindings for manual removal. After unbound, retain Client identity/credentials/history and enforce destination Lab name uniqueness. Never silently clear bindings.
68. **Q68 — Changing Client credentials disconnects users (B).** Show impacted SUT/RD/session counts, confirm, verify new credential per Q70, commit update then revoke affected UART Web links; don't kill tmux/minicom or external clients; no auto-reconnect.
69. **Q69 — Secrets non-viewable (A).** Even Super Admin cannot reveal or download existing SSH password/private key via UI/API; show method/configured state only. Change by replacement, never echo secret.
70. **Q70 — Validate replacement credential before storing (B).** Confirm trusted SSH host key and test SSH authentication with candidate password/key without remote shell, command or tmux. Only save on success; on failure retain previous credential/links. Audit safely.

### Q71–Q80: Client validation and temporary maintenance grants

71. **Q71 — Verify SSH on new Client before create (B).** Admin checks unique name/IP, trusted host fingerprint and actual SSH authentication before Client exists as enabled record. No persistent record on failure; no remote shell/tmux launch.
72. **Q72 — Verify Client IP/port change before save (B).** Test new endpoint with existing credential and verified host key, no shell/remote command; only commit if success; else retain old details and links. Confirm/disconnect affected links only on successful committed change.
73. **Q73 — Creating Admin approves initial Client host key (A).** Lab/Super Admin who creates the Client compares fingerprint with trusted source and explicitly confirms before authentication/create. Later RD may update under Q7.
74. **Q74 — Client host-key update revokes all its UART Web sessions (B).** RD sees old/new fingerprints and impacted SUT/RD/session counts; confirms change; commit audit+key and disconnect all associated UART Web links; no auto-reconnect, no remote tmux/minicom kill.
75. **Q75 — BMC host-key update revokes that SUT's BMC Web sessions (B).** RD sees/validates old/new fingerprint and impacted users, confirms; commit then disconnect associated direct BMC SSH links only. UART and external PuTTY unaffected, no auto-reconnect.
76. **Q76 — Maintenance/Out of Service does not inherently ban Console (B).** Keep console access according to Compose policy. Existing regular Claim/Queue/Reservation maintenance restrictions stay. Show operational state/reason; never implicitly grant writes.
77. **Q77 — Admin temporary maintenance Console grant (B).** Lab/Super Admin may grant named RD read/write to named Maintenance/Out of Service SUT without Claim even if claim_only policy. Does not create/modify Claim, reservation, queue or usage record; audit grant/revoke/expiry.
78. **Q78 — Grant durations up to 24 hours (B).** Administrator selects 1/2/4/8/12/24 hours. Explicit expiry, revoke when expired or state returns Normal, terminate affected sessions if no other authorization.
79. **Q79 — Grant reason optional (B).** Admin may provide reason, but grant without reason is allowed. Always audit admin, RD, SUT, created/expires and optional reason.
80. **Q80 — No grant notifications (A).** No in-app, email or Teams message on grant/revoke/expiry; admin tells RD separately. Console page may show one's effective active grant/expiry; revoke still closes unauthorized links.

### Q81–Q83: Multiple grants, extension and renewal

81. **Q81 — Multiple RD grants per SUT (A).** Independently authorize several RD for same Maintenance/Out of Service SUT, separate expiries and reasons; shared UART write per Q15. No duplicate concurrent active grants for same RD/SUT. Revoke one does not revoke others.
82. **Q82 — Extend active grant within original 24h (B).** Admin may extend before expiry, never beyond original created_at +24h. Extension keeps same creation timestamp; audit old/new expiry, no disconnect if continuously valid. After 24h requires fresh approval.
83. **Q83 — Immediate fresh grant after expiry (A).** No cooldown; Lab/Super Admin can create a distinct new grant with fresh max-24h window, never automatic renewal. Old grant and audit retained, expired Console does not auto-reconnect.

## 2. Cross-cutting deployment and permission policy (owner-confirmed outside numbered Qs)

- Runtime settings: CONSOLE_ENABLED=false by default; CONSOLE_ACCESS_POLICY=claim_only by default; accepted values claim_only, shared_readonly, all_authenticated. Invalid values fail startup; change via Compose environment plus container recreate, not rebuild.
- claim_only: current SUT Claim holder and appropriately authorized Admin read/write. shared_readonly: all active signed-in RD read-only, current Claim holder/Admin read/write. all_authenticated: all active signed-in RD read/write. Temporary maintenance grants of Q77 override the missing Claim only on their specific SUT while Maintenance/Out of Service; never permit inactive accounts.
- All active authenticated RD can edit/clear mapping and review connection history regardless of Claim, but cannot add/edit Client host, SSH port, credentials or Lab. RD can explicitly trust/update verified host keys under Q6/Q7.
- Two Labs: Client.lab_id must match SUT.lab_id for UART binding; no cross-Lab exception. One active Client/tmux name pair per SUT. Direct BMC SSH fixed port 22.
- HTTP intranet exception expressly accepted by owner: keep existing internal HTTP website and ws:// Web Console without corporate DNS/TLS certificate. Add CONSOLE_ALLOW_INSECURE_HTTP=false default, requiring explicit true to use Web Console over HTTP. Future HTTPS/WSS support remains. Never suggest that SSH encryption downstream protects browser-to-gateway credentials, cookies or terminal stream: those are plaintext/interceptable on HTTP/WS.
- Preserve existing host port 5088 and local persistent SQLite, image-only Docker Compose deployment, non-root application runtime. Feature flags OFF initially. Limit frontend routes to signed-in active user and policy authorization; protect WebSocket Origin, session, connection ticket, CSRF-bearing mutations and continued per-input rights checks.
- Restrict gateway to SSH-protocol connections only and prevent arbitrary shell pivot, SSH port forwarding or remote target injection. **BMC targets must belong to RFC1918 ranges**, but there is no specific Lab CIDR allowlist. Deny public IPv4 and dangerous private/special targets including gateway/host/container self-addresses, cloud metadata, loopback, multicast, broadcast, link-local and control-plane destinations. Validate when saving and immediately before connecting.
- Admin GUI manages encrypted Client secrets with key material separate from the SQLite backup, no reverse lookup. Plan secure backup/restore and rotation. No production secrets in public repo.
- HTTP-mode security acceptance requires explicit operator acknowledgement, LAN-only bind/firewall restrictions and tests proving no secrets in URLs/logs/storage. The remaining interception risk must be disclosed in the operator guide.

## 3. Normal user journey and operational semantics

1. User opens a SUT detail and selects Open Console (separate tab). If disabled globally, Console cannot start. If UART/BMC mapping absent, show Not Configured + Edit Connection.
2. User selects UART or BMC SSH, requests Connect. Check policy, quota, latest mapping, host-key trust; direct BMC prompts for credentials; UART securely uses its admin-configured Client identity and attaches only an existing named tmux session. Never create/kill tmux or minicom.
3. Display live terminal (ANSI, xterm-256color), connected state, unique Web RD participants, Shared Console warning if >1 UART RD, basic keys/search/clipboard/font/fullscreen. No persistent terminal transcript.
4. If endpoint mapping, Client IP/port/credentials/host-key or BMC host-key changes, confirm scope as applicable, atomically update and revoke only affected Web sessions, with clear reason and manual new connection. Never kill external PuTTY or persistent UART tmux/minicom.
5. Transient disconnect triggers bounded reconnection; keep tab buffer but do not replay input. Intentional Disconnect and invalidation never silently reconnect. Browser tab close gives best-effort beforeunload warning while connected/reconnecting.
6. Admin grants named RD temporary Console read/write for Maintenance/OOS up to 24h; grant checks are server-side. Existing reservation/Claim state transitions remain unchanged.

## 4. Data model and API design obligations (for Phase A; proposed, not yet approved schema)

- Reuse labs/suts/users and audit patterns; design console_clients with lab_id, normalized display name, globally unique IPv4, admin SSH port, auth method, secret ref, Host Key trust record, enabled, optional notes, versions and timestamps.
- Design SUT-to-Console Client mapping and tmux session string (not a mandatory managed serial-port inventory: because Q2 specifies user-input existing tmux name and Web does NOT create minicom). Optional physical ttyUSB/serial IDs may be displayed as admin notes but should not be mandatory prerequisites to Connect.
- Design independent BMC IPv4 endpoint with fixed port 22 and BMC host-key trust bound to SUT/target identity. Map edits must be versioned and individually auditable, with active unique Client+tmux constraint.
- Define durable security/audit entities for host-key history, Client credential reference/rotation, mutable mapping revisions, Web Console sessions, grant start/expiry/revoke/extension, and bounded authentication attempts. No per-writer lease under Q15.
- SQLite single-host write serialization and invariant tests; transaction boundaries must avoid external SSH I/O while DB write locks are held. When pre-save validation and commit are separated, recheck version, host identity, mapping and authorization to prevent TOCTOU.
- Define endpoint and WebSocket message schemas, login/Origin/ticket binding, secret-handling, size limits/backpressure, cancellation and disconnect semantics, and audit field allowlists.
- Explicitly reconcile fixed auth session expiry with Q12 no keyboard-idle disconnect: absence of idle cutoff does NOT extend or bypass login expiry.

## 5. Acceptance and regression checklist

- One Lab with multiple Client hosts, another Lab with multiple Client hosts; clients with one/many UART sessions, separate BMC SSH, duplicate-pair and duplicate-IP rejection, same-Lab name uniqueness and cross-Lab binding denial.
- SSH password/key Client onboarding and rotation: verified host key plus credential first, failure keeps old version; never expose existing secrets. Admin-only edit; RD host-key trust updates with old/new fingerprint, audit and session invalidation.
- RD BMC IP/mapping self-service and clearing, separate endpoint Save, optional reasons, immutable history, concurrent edit detection, affected-session confirmation and revocation scope.
- Three Compose policies; inactive user/session revocation, protected WebSocket Origin, temporary grant cases and expiry/restoration, per-user 10-session cap and multi-tab concurrency.
- Only existing tmux session attach, simultaneous read/write, external tmux unaffected, no automatic remote commands, terminal state after reconnect, 10k scrollback and no persistent terminal content.
- Verify Q16/Q34/Q38/Q41/Q46/Q50 terminal UI functionality under Chromium; clipboard fallback documented; direct BMC auth prompts and attempts per Q43/Q44.
- Fixed 10-second connect timeout, bounded reconnect, clear user errors, no background SSH checks, no live Client tests on mapping Save; Client admin create/change testing is mandatory per Q70–Q72.
- Explicit HTTP/WS insecure-mode opt-in; deny public BMC IPv4 and self/sensitive targets, including sensitive private-range destinations; transport-risk banner/documentation; verify login/secret nonlogging. Test HTTPS/WSS compatibility separately.
- All preexisting SUT business-rule regressions continue to pass. No real BMC/Client commands in CI; use mock SSH/tmux fixtures. Production pilot requires explicit authorization.

## 6. Deferred decisions / implementation notes (NOT another owner Q&A checklist)

- Q84 early revocation UX was NOT owner-confirmed: Q77 already permits admin revoke; engineering baseline may implement confirm-then-immediately-revoke, re-evaluating other authorization sources, but label it an unconfirmed implementation default.
- Clarify initial Console Client helper deployment/remote tmux socket permissions without modifying existing daemon-owned tmux/minicom; honor only-attaches-existing-session.
- Reevaluate whether WebSocket over insecure HTTP may be exposed given the user's explicit risk acceptance; do not silently replace the policy with HTTPS-only or claim that HTTP is secure.
- Host-key confirmation is not proof without independently trustworthy fingerprint source; provide fail-closed and audit, never trust automatically.
- A single backend may be inappropriate as a broadly privileged gateway; Phase A must propose privilege separation, secret encryption/rotation, egress boundaries and rollout gating.

## 7. Workflow and change control

1. This file is the owner decision source of truth. Codex must read it completely before designing or implementing CONSOLE-001; no truncation or implicit omissions.
2. Phase A must produce separate architecture, schema/migrations design, security threat model, interface contracts, acceptance matrix and compatibility plan; do NOT implement live SSH, modify production hosts or publish image in Phase A.
3. Any discrepancy among AGENTS.md, SPEC.md and this new approved-scope feature must be raised explicitly and resolved in a reviewed scope amendment. Do not silently violate coordination-only MVP scope.
4. Submit documentation PR for owner review; do not auto-merge, auto-release, connect to production SUTs or update real secrets.

