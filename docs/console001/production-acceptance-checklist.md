# CONSOLE-001 operator acceptance checklist

Review date:2026-11-05 (Asia/Taipei). **NOT EXECUTED on company infrastructure.**
Every checkbox below is pending operator evidence; synthetic tests do not sign it.
Use [readiness](rc-readiness.md), [pilot scope](pilot-plan.md),
[GO/NO-GO](release-go-no-go.md), [runbook](operator-runbook.md) and
[recovery](rollback-and-recovery.md). This is a future checklist, not authorization
to connect, activate HTTP/WS or deploy from Codex Cloud.

## Acceptance record and evidence rules

- [ ] A named owner authorizes the one-Client/one-test-SUT scope, time window,
  operator, two authorized RD testers, independent fingerprint/key custodians and
  rollback authority. Record approvals in the private change record.
- [ ] Record exact source SHA, Git tag, registry index/platform digest, image OCI
  version/source/revision, Compose SHA256s, policy revision, schema head and key IDs.
  No mutable latest/stable or Web-only image-lock override substitutes for a digest.
- [ ] Record each case as PASS/FAIL/BLOCKED/NOT RUN, tester/reviewer, Taipei timestamp
  and sanitized evidence reference. A blank or unavailable item is not PASS. Keep
  private inventories, credentials, DBs and contact details outside GitHub.
- [ ] No terminal transcript, keystroke/clipboard capture, credential screenshots,
  SSH debug/body logs or secret environment dumps. Use counts, safe reason codes,
  independent fingerprints, session metadata and synthetic marker assertions.
- [ ] R1 browser validation instability in readiness is resolved by reviewed evidence;
  hosted CI at the exact RC source and required isolated checks are green.

## C3 — actual Client topology and accepted Linux authority

- [ ] C3-01: Identify the preconfigured fixed SSH account and auth method for the
  one authorized Client. Admin provisions its password/key out of band; no root SSH
  requirement, agent/GSS/X11/TCP forwarding or browser-selected identity/host.
- [ ] C3-02: Local Client administrator reviews account groups, sudo, files,
  interactive shell startup, network reach and shared-session/hardware privileges.
  Sign acceptance that remote shell commands may affect hardware/other sessions.
  Gateway audit cannot attribute individual commands to RD; there is no writer lock.
- [ ] C3-03: Verify existing tmux/minicom is already alive, owned by/access-controlled
  for that account, using its default socket. Record versions and socket owner/mode/
  ACL in private evidence. Custom socket or different-owner access is BLOCKED until
  separately validated; no automatic ownership repair/session rename is allowed.
- [ ] C3-04: Exact configured existing name passes current64-character ASCII grammar.
  First Connect attaches that session only, TERM=xterm-256color. Negative missing
  name yields failure/Edit/Retry without creating tmux/minicom or another session.
- [ ] C3-05: Two authorized writers see synthetic output and can both input; names
  and distinct-user count are correct. Two tabs by one RD count once as participant
  but twice for quota. A read-only viewer selects/copies/searches/resizes without
  transmitting input, paste, keys or automatic emulator responses.
- [ ] C3-06: Native tmux keybindings work; Detach leaves the same SSH connection in
  the ordinary interactive shell. Use only explicitly approved harmless commands.
  Do not test power/firmware/other-session destruction as an acceptance shortcut.
- [ ] C3-07: Disconnect/close one tab leaves peers and original tmux/minicom alive;
  no Gateway-initiated creation, killing, restart, rename or reconfiguration, and
  no deliberate impact to external PuTTY users. Native sizing is not overridden.
- [ ] C3-08: Output-only/background operation, real login expiry and network loss/
  fresh reconnect behave as specified. No idle keyboard cutoff, no replay, no
  auto reconnect after explicit Disconnect/revocation. Verify bounded retry/failure
  feedback and tab-only buffer/boundary; remote ANSI repaint is documented and
  must not be confused with a persistent transcript guarantee.

## C4 — restricted internal HTTP/WS and host security

- [ ] C4-01: Security/owner/operator explicitly approve this site's plaintext
  credential, cookie, ticket, Admin key-upload, clipboard and shell-stream risks.
  Downstream SSH/encryption-at-rest/CSRF/HttpOnly do not encrypt HTTP/WS or prevent
  LAN JS replacement. Do not inherit generic owner design approval as site approval.
- [ ] C4-02: Before any live activation, prove fresh config stays false/claim_only/
  insecure HTTP false. Normal coordination works with no Broker or Console keys.
- [ ] C4-03: Only after a separately authorized change, record deliberate Console
  enablement, explicit insecure HTTP true and the exact risk acknowledgement.
  Leave all_authenticated off initially; COOKIE_SECURE=false is only for the
  approved HTTP site. Missing attestation/invalid booleans/policy/Origin deny startup.
- [ ] C4-04: Bind only the selected private LAN interface, Host5088→Container80.
  Prove authorized client access and denied unapproved VLAN/public access through
  host firewall/routing controls. No public port forwarding or Docker API exposure.
- [ ] C4-05: Review all host aliases/routes, Docker/container/control-plane networks,
  metadata and sensitive endpoints in the private deny policy. Prove raw Broker
  sockets cannot reach negative test services on those paths, not just API refusal.
  Do not actually probe sensitive company endpoints; use authorized substitutes.
- [ ] C4-06: Web PID10001/Broker10002 have zero capabilities/no-new-privileges and
  read-only roots. Namespace keeper PID10003 drops privileges after scoped root
  NET_ADMIN initialization; no host networking, privileged container or Docker
  socket mount. Broker has no DB/public port; Web has no KEK; private IPC is peer-UID,
  HMAC, boot/replay/deadline protected. Do not treat a socket-only healthcheck as auth.
- [ ] C4-07: Missing/bad IPC/policy/KEK and a valid-format wrong KEK fail authenticated
  startup preflight; no new key generation/fallback. Broker death fences live input
  via leases; pending revocations remain pending until ACK, never manually faked.
- [ ] C4-08: Review boot ordering before Docker auto-restart: missing/wrong /data
  mount fails without writing an empty DB. A Compose unit merely ordered after
  Docker is insufficient. Recreate the full namespace→Broker→Web stack on policy/
  namespace changes; review shutdown and host restart procedures independently.
- [ ] C4-09: Exact Origin, forged/null/cross-origin/replayed ticket/CSRF/query-secret
  rejection; no arbitrary forwarding/exec/target selector. Clipboard denied over
  LAN HTTP falls back to Ctrl+V without weakening browser protections.
- [ ] C4-10: If choosing future HTTPS/WSS, separately approve/test certificate trust,
  proxy peer/scheme configuration and no downgrade. Current real TLS/WSS deployment
  is unverified; do not enable trusted forwarded headers broadly to make it pass.

## C5 — independent fingerprints and incident process

- [ ] C5-01: Independent custodian supplies Client and BMC algorithm/exact SHA256
  fingerprints via physical/management console or independently authenticated
  signed inventory. Network key discovery/keyscan alone is not OOB verification.
- [ ] C5-02: Admin initially approves Client pin; no credential is sent to an unknown/
  changed key. Actual handshake requires exact accepted key and server possession;
  failed/stale evidence retains old credential/details/links, no accept-any/TOFU.
- [ ] C5-03: Active RD retains Q6/Q7 approval authority; show target/IP/port,
  old/new fingerprints, exact impacted SUT/RD/session counts and explicit OOB
  acknowledgement. Test cancellation, stale CAS and concurrent impacted-generation
  change; never bypass confirmation merely because displayed counts are unchanged.
- [ ] C5-04: With separately authorized disposable pins, Client replacement revokes
  all its UART Web links, BMC replacement only that SUT/BMC; no automatic reconnect,
  other transport disruption, tmux/minicom kill or Claim/queue/booking changes.
- [ ] C5-05: Audit is actor/target/revisions/fingerprints/result only. Train incident
  escalation for unexpected key change; stop/fence access and verify independently
  before accepting. Malicious/mistaken RD trust replacement remains a signed
  residual risk; checkbox+audit is not proof of endpoint identity.

## BMC target/authentication

- [ ] BMC-01: Strict canonical RFC1918 IPv4, fixed22, no Lab CIDR allowlist. Reject
  public, loopback/link-local/metadata/sensitive self/host/container targets and
  disguised IPv4/DNS/IPv6. Save and immediate pre-connect checks both apply.
- [ ] BMC-02: Use only the authorized test SUT's synthetic/test BMC account after C5.
  Prompt every auth flow; three explicit attempts, fresh flow/reconnect prompts
  again, no automatic password retry or cross-flow lockout added by Gateway.
- [ ] BMC-03: Wrong credentials/key/timeout fail safely; no shell/PTY/commands during
  Client Admin auth-only validation. No BMC username/password in DB/audit/storage/
  URLs/logs. Remote BMC lockout/legacy algorithm constraints are independently reviewed.

## Session authorization and UI

- [ ] AUTH-01: claim_only: current holder/Admin RW, other RD denied. Reservation or
  queue membership alone is not a Claim; inactive/must-change/expired users denied.
- [ ] AUTH-02: Separately approved test switches verify shared_readonly RO/RW and
  all_authenticated RW; restore claim_only afterwards. UI hiding is not security:
  forge direct input/paste/mouse/key frames and prove both Gateway/Broker deny RO.
- [ ] AUTH-03: Mapping/history editable by active RD independently of terminal
  policy, but Client host/port/credential/Lab/enabled inventory stays Admin-only.
  Same-Lab and unique active Client/tmux pair/IP/name invariants resist concurrent saves.
- [ ] AUTH-04: Mapping clear/edit, Client disable/IP/port/credential and Host Key
  changes show exact impact, commit/audit/revoke the correct transport only. No
  automatic live probe on mapping save; Client candidate auth before storing.
- [ ] AUTH-05: Named maintenance grants1/2/4/8/12/24h; independent users, expiry,
  extension <=original24h, revoke and Normal transition. Recompute alternate rights;
  expired links never heal from a new grant. No grant notices or coordination edits.
- [ ] AUTH-06: Ten sessions/user across transports/tabs;11th rejected, reconnect
  same slot, stale close cannot free successor, lost tab cleanup bounded. Own session
  list has no other-tab kill/private user enumeration. Distinct participants correct.
- [ ] AUTH-07: Logout/password reset/change/account disable/role/Claim loss, archive,
  mapping/trust revisions and Broker restart revoke/downgrade as appropriate. No
  old generation can input or reopen automatically; already delivered bytes cannot
  be recalled. SSH shared-account processes are outside Gateway kill authority.
- [ ] UI-01: Separate noopener tab; six states, Not Configured/Edit, UART/BMC switch
  requires Connect. ANSI hostile OSC/link output safe; fullscreen/Esc, resize,
  font14/integer10–24, case-insensitive local search and10k trim work.
- [ ] UI-02: Single/multiline paste count/preview/confirm/cancel/hidden-control/size
  gates, five Send Keys once, RO/disconnected block, copy/scroll/mouse behavior,
  foreground focus/no background steal and best-effort native unload warning.
  Reload loses font/output; no terminal recording/download/Clear Screen control.

## Data, custody and rollback

- [ ] DATA-01: Keep persistent SECRET_KEY and UID10001/0700 SQLite bind at the intended
  /data filesystem; no production DB, private policy or credential in source/image.
- [ ] DATA-02: Stop writers for cold backup; preserve complete DB/WAL state and
  image/config/schema manifest. Separate DB backup custody and offline versioned
  KEKs; test independent retrieval without printing secret material.
- [ ] DATA-03: KEK rewrap one-shot is network-none with separate DB, read-only staged
  key and backup-manager-controlled `/run/backup` mount. Backup is not under
  `/app/data` or KEK directory; exclusive new0600 file, private0700 directory. Wrong
  key/AAD and mid-batch failure preserve prior DB; verify no credential reveal.
- [ ] DATA-04: On a copy, upgrade prior compatible image/DB to candidate; compare
  account IDs/password hashes, Labs/SUTs/usages/history/queue/reservations and
  intended deadline transitions. Verify migration head, integrity/FKs, no data reset.
- [ ] DATA-05: Restore into an empty separate directory with correct ownership and
  matching image/keys/schema. Roll back old image only with its compatible pre-upgrade
  backup, never overlay old DB onto new WAL or assume backward schema compatibility.
- [ ] DATA-06: Console paired upgrades use the runbook; setup refuses Console stacks.
  No automatic Named Volume migration/deletion, secret replacement, admin bootstrap
  repetition, moving tag-follow recreation or automatic schema downgrade.

## Final signature

- [ ] Named technical reviewer, owner/security, operator, Client administrator,
  fingerprint custodian and backup/key custodians approve their respective evidence.
- [ ] Every failure has a corrective action/retest reference. No unanswered blocking
  case is waived implicitly. Update [GO/NO-GO](release-go-no-go.md) per boundary;
  wider rollout needs new approval even after a successful one-SUT pilot.
