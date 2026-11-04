# Milestones, fixtures and acceptance matrix

All rows below are PLANNED / NOT EXECUTED Console acceptance tests. Phase A validates documentation coverage only. IDs Q1–Q83 refer to [unchanged owner ledger](../CONSOLE_001_REQUIREMENTS.md); no row replaces its full wording. A pass requires observed behavior and retained evidence, not a checkmark from design prose.

## Phase B–E plan

| Phase | Implementation slice after review | Required exit evidence |
|---|---|---|
| B — foundations | Feature-OFF typed settings; additive ORM/Alembic after current head; encryption/keyring abstraction with fake broker; Client/mapping/trust/grant services and versioned metadata contracts; quota/ticket allocation; no real SSH | H2/H4/H5 reviewed; old-data preservation and empty migration, schema diff, FK/integrity and rollback rehearsal; all policy/grant/concurrency/crypto negative tests; no secret echo, no network on migration/mapping Save; existing suite green |
| C — broker/SSH | Isolated mock-SSH then disposable fake Client/BMC adapters, key challenge/auth-only verification, trust pinning, restricted existing tmux helper proof, WS authorization/fences/backpressure/crash recovery | D1 resolved; H1/H8 reviewed/proven; fixed10s timing,3 attempts/flow,10slot race, version/trust TOCTOU and commit/crash fault injection; no forwarding, alternate target, create/kill commands or terminal logs |
| D — terminal/admin UX | Local maintained xterm.js standalone page, mode switch/status/reconnect, participants, read-only enforcement, paste/search/font/fullscreen, mapping/history, Client secret replacement and own session list | Chromium end-to-end at desktop/mobile; Q11–54 affordances, HTTP clipboard fallback and HTTPS clipboard separate; CSRF/Origin/IDOR/secret-redaction tests; existing Dashboard/Calendar/Inbox unchanged |
| E — hardening/pilot | Source/image-only Compose and reviewed broker/key mounts/installer, key rotation/backup/restore, HTTP opt-in and TLS compatibility, resource soak, authorized production pilot | Full regression/security matrix; immutable image provenance and anonymous digest validation only under separate release authorization; LAN/firewall/self-target controls and two-RD UART pilot accepted; operator sign-off and recovery tested |

One focused PR per phase or reviewed sub-slice; no auto-merge/release. Phase A does not add dependency pins, code, mocks, migrations, routes, UI, Compose variables or secrets. Phase B begins only on explicit next-phase authorization after design review.

## Fixture catalogue

- F1 isolated SQLite: two fictional Labs, multiple Clients per Lab, Client with one/many UART bindings, mixed password/key identities, same session name on different Clients, case/name/IP collisions including disabled Clients, archived SUT, IPv6 legacy inventory preserved, all coordination states and login lifetimes.
- F2 in-process mock broker/SSH server: deterministic host keys and changed/unknown/rotated variants, auth success/failure/timeout, credential-sent observer, read-only byte counter, no-shell authentication recorder, no forwarding/subsystems, cancellation and output flood. No real network targets or production credentials; test transport destinations are isolated fixtures with explicit test-only network adapters, not weakening production deny logic.
- F3 disposable tmux/minicom simulator: pre-created session/socket/pane, externally attached fake PuTTY client, unusual names, permission failure, missing server/session/pane, multiwriter traffic and terminal controls. Assert no start/new/kill/minicom launch, no socket/config permission modifications, remote process identity survives Web disconnect/revoke. Separately gate actual helper compatibility on a disposable tmux version matrix.
- F4 deterministic time/faults: login expiry, grant boundary and state Normal race, Client/mapping/trust mutation versus ticket/open/input, quota11th, process crash before/after DB commit/broker fence, duplicate revocations, missed heartbeat, restored backup and root-key rotation CAS.
- F5 Chromium: signed-in RD A/B, Lab Admin/Super Admin, inactive/must-change/expired users, mocked Clipboard/Fullscreen failures, background tab timers, malicious terminal escape output, denied Origin/CSRF, memory-only search/scrollback and keyboard navigation.
- F6 isolated deployment: image-only Compose5088:80 non-root, original SQLite bind, separate keyring/broker isolation, LAN HTTP opt-in ON/OFF and proxy HTTPS/WSS, metadata/self/NAT egress deny, backup/key mismatch, old encrypted backup after rotation. No public ingress or real device connection.

## Q1–Q83 traceability

| ID | Planned observable acceptance / negative case | Design location | Phase / fixture |
|---|---|---|---|
| Q1 | Distinct Client fixed identity; UART RD never prompted for it | security.md | B,C/F1,F2 |
| Q2 | RD chooses registered same-Lab Client and manually enters validated existing tmux name, no session inventory prerequisite | contracts.md | B,D/F1,F3,F5 |
| Q3 | Fresh BMC username/password each authentication, absent from storage/logs/URL/audit, purged after attempt | security.md | C,D/F2,F5 |
| Q4 | Mapping commit fences/closes affected Web links only; external process identity unchanged | architecture.md | C/F3,F4 |
| Q5 | No Lab CIDR allowlist; syntactically invalid/special/self targets rejected before dial; globally routed case pending D1 | security.md | B,C,E/F2,F6 |
| Q6 | Active RD BMC unknown/changed-key comparison before credential; old/new audit, no auto trust | security.md | C,D/F2,F5 |
| Q7 | Active RD Client trust replacement with impact warning; no credential before trust | security.md | C,D/F2,F5 |
| Q8 | Mixed Client password/private-key onboarding and use, unsupported key fails safely | schema.md | B,C/F1,F2 |
| Q9 | Admin GUI replacement encrypted with independent root, no plaintext SQLite | security.md | B,D/F1,F5 |
| Q10 | No terminal input/output recording, export or download; metadata only | security.md | C,D,E/F2,F5,F6 |
| Q11 | Open Console from Detail in separate spacious page/tab | contracts.md | D/F5 |
| Q12 | No keyboard activity required for output; login expiry still closes | architecture.md | C,D/F4,F5 |
| Q13 | Finite backoff, manual fallback, revalidate each attempt; no input/credential replay or revocation reconnect | architecture.md | C,D/F2,F4,F5 |
| Q14 | Same RD two tabs counts once; names/modes visible; no PuTTY-user claim | architecture.md | C,D/F3,F5 |
| Q15 | Two authorized UART writers both send; Shared Console warning, no lease/latest-typist record | architecture.md | C,D/F3,F5 |
| Q16 | Single-line paste direct, multiline count/preview confirmation, controls handled, read-only rejects | contracts.md | C,D/F2,F5 |
| Q17 | Reconnect keeps tab scrollback/boundary; refresh loses it, no persistence/missed-output promise | architecture.md | D/F5 |
| Q18 | Initial Not Connected; no SSH/ICMP/session probe until explicit action, live heartbeat only | architecture.md | B,C/F2 |
| Q19 | Error offers Retry/Edit; Client auth failure contact admin, missing tmux mapping edit, no target fallback | contracts.md | C,D/F2,F5 |
| Q20 | Cross-Lab binding blocked for RD and both admins, including concurrent Client move | schema.md | B/F1,F4 |
| Q21 | Concurrent same Client/tmux pair conflict names existing SUT; other Client allowed; inactive binding releases slot | schema.md | B/F1,F4 |
| Q22 | Empty reason accepted; actor/time/old/new audited | schema.md | B/F1 |
| Q23 | All RD read mapping history including archive, no secrets | contracts.md | B,D/F1,F5 |
| Q24 | No history restore button/API; manual re-edit revalidates/revokes | contracts.md | B,D/F1,F5 |
| Q25 | BMC fixed22; malicious custom port rejected | contracts.md | B,C/F2 |
| Q26 | Both unconfigured modes visible with Edit; OFF hides/disables all Console entry, no SSH | contracts.md | B,D/F2,F5 |
| Q27 | Switch closes only current attachment; other mode requires Connect/new BMC auth | architecture.md | C,D/F2,F5 |
| Q28 | Multiple same/different SUT tabs/transports independent within quota; one tab close preserves others | architecture.md | C,D/F3,F5 |
| Q29 | Ten active slots accepted; simultaneous11th denied; reconnect not double-counted; lost-tab cleanup | schema.md | B,C/F4 |
| Q30 | Own read-only list N/10, SUT/Lab/mode/time/status/link; no other-tab kill or cross-user inventory | contracts.md | B,D/F1,F5 |
| Q31 | Fullscreen/Esc adjusts PTY without disconnect; unsupported API fallback | contracts.md | D/F5 |
| Q32 | A+/A− default14,10..24 step1 updates PTY sizing | acceptance.md | D/F5 |
| Q33 | Reload/new tab defaults14, no browser/profile preference | acceptance.md | D/F5 |
| Q34 | Focused Ctrl+F case-insensitive previous/next/highlight in buffer, no regex/persistence/remote input | acceptance.md | D/F5 |
| Q35 | 10,000 lines trimmed oldest; high-throughput bytes also bounded/backpressured | contracts.md | C,D/F2,F5 |
| Q36 | All six specified states, Retry/reason, input only Connected; no RTT widget | contracts.md | D/F5 |
| Q37 | Background tab output continues within browser limits; sleep loss/reconnect handled honestly | architecture.md | C,D/F4,F5 |
| Q38 | Maintained ANSI emulator, cursor/colors/interactive sequences, no custom ANSI parser/theme | security.md | D/F5 |
| Q39 | PTY requests xterm-256color, no picker or remote setting change | architecture.md | C/F2,F3 |
| Q40 | Native multi-client sizing/crop, no120x40 or global tmux resize policy override | architecture.md | C,D/F3,F5 |
| Q41 | Focused Ctrl+C/D/Z/arrows/Tab/Enter; Ctrl+F local, reserved browser shortcuts respected; forged read-only input denied | contracts.md | C,D/F2,F5 |
| Q42 | Exactly10s establishment budget both transports, human prompt time excluded, no idle limit/fallback target | architecture.md | C/F2,F4 |
| Q43 | Three explicitly submitted BMC auth attempts/flow; password discarded each; Client failure immediate | contracts.md | C,D/F2,F5 |
| Q44 | New flow has no rolling failed-password lockout, no auto brute force; in-flight cap and safe audit | architecture.md | B,C/F2,F4 |
| Q45 | Writable first connect focuses; read-only/background reconnect doesn't steal focus | architecture.md | D/F5 |
| Q46 | Best-effort beforeunload only Connected/Reconnecting; cancel leaves link; suppressed prompts acknowledged | acceptance.md | D/F5 |
| Q47 | Disconnect immediate current link only, no confirmation/retry; retains output, correct counters | architecture.md | C,D/F3,F5 |
| Q48 | Esc/Tab/Ctrl+C/D/Z only Connected writable, exactly once, no advanced hardware key | contracts.md | C,D/F2,F5 |
| Q49 | Select/copy/scroll/native mouse behavior, no Mouse Mode setting; read-only select but no mouse-byte bypass | contracts.md | D/F5 |
| Q50 | Right-click gesture attempts paste, multiline guard, HTTP permission failure/Ctrl+V fallback; read-only rejects | security.md | D/F5,F6 |
| Q51 | No extra Clear Screen control/API | contracts.md | D/F5 |
| Q52 | Reconnect always visible, disabled during Connecting/Reconnecting; fresh current attachment, same slot, no replay | contracts.md | C,D/F4,F5 |
| Q53 | Connected reconnect confirmation/cancel; Failed/Disconnected no extra confirmation; tmux survives | contracts.md | C,D/F3,F5 |
| Q54 | Safe understandable failures/action, no raw stack/secret echo | contracts.md | C,D/F2,F5 |
| Q55 | No Test Connection button/probe on mapping Save; admin Q70–72 still live verification required | contracts.md | B,C,D/F2,F5 |
| Q56 | Active impact preview counts/confirm; zero-impact direct save rechecks racing admission/version | architecture.md | B,C/F4 |
| Q57 | UART/BMC independently versioned/saved/revoked; other transport uninterrupted | schema.md | B,C/F4 |
| Q58 | RD clears each mapping to Not Configured, confirmation/history/revocation, no remote/SUT deletion | contracts.md | B,C,D/F1,F3 |
| Q59 | Admin disable while bound closes UART, denies new, retains mappings/history; reenable verifies normally | architecture.md | B,C/F1,F3 |
| Q60 | Disabled Client absent new selections; retained disabled binding visible, clear/reassign allowed | contracts.md | B,D/F1,F5 |
| Q61 | Only admin Client IP edit, same ID/associations, impact confirmation, verify new identity, revoke on success | schema.md | B,C/F1,F2,F4 |
| Q62 | Admin Client port22 default/1..65535, validate/revoke change; BMC port immutable | contracts.md | B,C/F2 |
| Q63 | Client IPv4 only; DNS/FQDN/IPv6/alternate encodings rejected | security.md | B,C/F2 |
| Q64 | Required admin Client name case-insensitive unique within Lab, same name other Lab allowed; safe rename | schema.md | B/F1,F4 |
| Q65 | Global Client IP uniqueness includes disabled/cross-Lab/different port, concurrent reject | schema.md | B/F1,F4 |
| Q66 | Optional notes visible RD, audited edit, zero disconnect | architecture.md | B,D/F1,F5 |
| Q67 | Admin move refuses incompatible bindings with list, never unbinds; unbound move retains ID/secret/history, destination-name check | schema.md | B/F1,F4 |
| Q68 | Credential change counts/confirm/test, successful commit revokes UART only/no auto reconnect; failure retains links | architecture.md | B,C/F2,F4 |
| Q69 | Even Super Admin cannot reveal/download existing password/key; replace only | security.md | B,D/F1,F5 |
| Q70 | Replacement auth with trusted key before save, no shell/command/tmux; failure old secret retained, safe audit | security.md | C/F2 |
| Q71 | New Client unique/pretrusted/auth verified before enabled create; failure no persistent Client | schema.md | B,C/F1,F2,F4 |
| Q72 | IP/port candidate verifies current credential+pinned new identity; failure old details/links intact | security.md | C/F2,F4 |
| Q73 | Creating admin explicitly approves initial key before authentication; RD initial-create denied | security.md | B,C/F2 |
| Q74 | RD Client key update old/new/counts confirmation; atomic audit/revoke all Client UART, no remote kill/retry | architecture.md | C,D/F3,F4,F5 |
| Q75 | RD BMC key update explicit comparison/counts; revoke that SUT BMC only, UART/PuTTY unaffected | architecture.md | C,D/F3,F4 |
| Q76 | Maintenance/OOS Console per policy; state/reason displayed, no implicit write or ordinary Claim bypass | architecture.md | B,D/F1,F5 |
| Q77 | Admin named RD/SUT grant read/write without Claim in non-normal states; coordination rows unchanged | architecture.md | B/F1,F4 |
| Q78 | Only1/2/4/8/12/24h initial durations; exact expiry/revoke/Normal closes when no other rights | schema.md | B,C/F4 |
| Q79 | Optional blank grant reason succeeds; admin/RD/SUT/time/reason audit always | schema.md | B/F1 |
| Q80 | No notification rows/email/Teams on grant/revoke/expiry; own grant expiry visible | contracts.md | B,D/F1,F5 |
| Q81 | Multiple RD separate grants, no duplicate active same RD/SUT; revoke one preserves others, shared writers | schema.md | B,C/F3,F4 |
| Q82 | Extension before expiry CAS, original created_at retained, <=original+24h, audit old/new, no unnecessary disconnect | schema.md | B,C/F4 |
| Q83 | Fresh distinct grant immediately after expiry, no cooldown/auto renewal/reconnect; old history intact | schema.md | B,C/F4 |

## Unnumbered cross-cutting acceptance

| ID | Mandatory planned verification |
|---|---|
| X1 | Default OFF/claim_only/insecure=false; invalid flags/policy fail startup; Compose recreate applies changes without rebuild; no current Compose edit in A |
| X2 | Complete three-policy matrix for all three roles, Claim/no Claim, active/inactive/must-change/expired login, grants/expiry/state Normal, archive and Client disabled; forged control/read-only frames rejected |
| X3 | Exact Origin, login cookie, first-frame one-use ticket, tab/login/version binding, CSRF and handshake timeout; per-input and output-only revocation, no secret in URL/storage/logs |
| X4 | HTTP opt-in refusal/success and warning, LAN-only bind/firewall, plaintext-risk acknowledgement, no false SSH-protects-browser claim; HTTPS/WSS separate compatibility and proxy-header spoofing tests |
| X5 | Canonical target/special/self/metadata/NAT deny, no Lab CIDR allowlist, protocol SSH only; D1 public-target interpretation recorded before relevant pass |
| X6 | Independent encryption root, no reveal, rotation CAS/restart, key/tag mismatch fail closed, old-backup recovery with correct key; no real secret in repo |
| X7 | SQLite single writer, no SSH I/O under write lock, DB uniqueness/trigger integrity, confirmation impact TOCTOU, postcommit invalidation and crash catch-up |
| X8 | Existing coordination regression suite green, HTTP30s polling unchanged, port5088/non-root/security/SQLite bind/image-only installer preserved, feature OFF behavior unchanged |
| X9 | No real BMC/Client CI, no automatic power/firmware controls, no tmux/minicom creation/termination, no external PuTTY disruption, no terminal recording |
| X10 | Design approval ≠ runtime approval; no Phase A implementation, migration execution, image publication, production secret/deployment modification or auto-merge |

## Production rollout gates (all remain unchecked)

- [ ] Owner reviews design/scope amendment and resolves D1 plus schema/topology assumptions; no silent requirement substitutions.
- [ ] Phase B/C evidence proves migration preservation, encryption/key recovery, helper confinement and egress enforcement; independent security review of elevated gateway exposure.
- [ ] Full matrix and existing regressions pass; no production data in fixtures, no secret/terminal content in logs, reviewed pinned dependencies/addons.
- [ ] Image-only clean install, upgrade and isolated recovery retain5088:80, UID10001, original SQLite bind/config, one worker; independent keyring custody documented and exercised.
- [ ] Explicit operator HTTP risk acknowledgement, coherent cookie/Origin/proxy configuration, LAN-only bind/firewall and sensitive-self/NAT deny tested; HTTPS/WSS compatibility separately demonstrated.
- [ ] Trusted fingerprint source and pre-provisioned helper/socket account reviewed per Client; no web installer or daemon change.
- [ ] Separate authorization for release and named production pilot; feature OFF by default, then small two-RD UART/BMC pilot with resource/session revocation checks and stop criteria.
- [ ] Pilot stop: unexpected target access, wrong-key credential transmission, lost revocation/fence, quota leak, unbounded queue, remote tmux disruption or coordination regression disables Console and closes Web attachments. Preserve metadata evidence; never auto-release SUT or kill remote daemons.
- [ ] Owner accepts residual HTTP interception, RD host-trust authority, no Lab allowlist, shared writers and remote shell privileges; production backup/recovery sign-off. No automatic stable promotion or production enablement.
