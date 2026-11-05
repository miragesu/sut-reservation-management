# Scope amendment, contradictions and engineering review register

Owner feature decisions are already captured in the immutable
[baseline](../CONSOLE_001_REQUIREMENTS.md); this review does not reopen them or
substitute rejected alternatives. New design choices below are **not** owner Q84+
answers. Phase A documentation review is distinct from implementation approval.

## Explicit compatibility amendment proposed by this PR

| Existing requirement/source | New approved requirement | Reviewed treatment |
| --- | --- | --- |
| AGENTS explicit product boundary; SPEC§5 and BR-017; PLAN ground rules ban SSH/BMC/device control | New explicit browser debug SSH/UART feature | Keep BR-001–BR-028 coordination-only semantics, add a separately gated Console exception. Revoking a Web attachment is not physical access lockdown or forced usage handover. No automated power/Redfish/IPMI/firmware actions. Manual remote shell may have hardware privileges: disclose, don't claim gateway prevents all typed commands. |
| AGENTS BR-018, SPEC BR-018/027, PLAN polling ban WS/SSE | Authenticated Console WS is necessary | Exception only for standalone terminal. Existing30s read-only Dashboard/Detail/Inbox polling unchanged; Console socket is not a new scheduling mutation or global notification system. |
| Inventory `suts.bmc_ip` is Admin-only and accepts IPv4/IPv6 | Active RD edits direct BMC IPv4 and UART mapping | Separate ConsoleBmcEndpoint, no auto-import/backfill or RD inventory PUT privilege. IPv4/fixed22 for Console; legacy inventory display and admin ownership unchanged. |
| SPEC§3/BR-008 only Super Admin manages users/system config | Lab Admin manages Client secrets/infrastructure; RD may accept host keys | Add narrowly scoped Console permissions, not global config/user administration. Both Admin roles retain existing all-Lab scope; UART same-Lab binding still absolute. |
| App credentials were only nonreversible Argon2id login hashes | Client needs recoverable encrypted password/private key | Separate encryption root, replacement-only Web GUI, no reveal path; Argon2id login hashes/SECRET_KEY rules unchanged. |
| Original warnings say HTTP is coordination LAN only | Owner explicitly accepts opted-in HTTP/WS terminal | Preserve opt-in false defaults, disclose plaintext risks, LAN controls; do not impose hidden HTTPS-only requirement or claim SSH protects HTTP. Future WSS supported. |
| Maintenance blocks new Claim/Queue/Reservation | Q76–83 allow Console/grants during unavailable state | Independent policy; no implicit Claim/booking edits, notifications or hardware actions. Normal transition revokes grants; other auth sources re-evaluated. |
| No forced disconnection of physical use | Q4/68/74/75 require immediate scoped Web revocation | Close only gateway-owned WS/SSH attachments, never tmux/minicom or PuTTY; do not Release current usage or clear existing queues. |
| Existing no per-user SUT ownership cap (BR-007) |10 simultaneous Web Console sessions/user | Count logical Console attachments, not Claims/SUT ownership. Do not change BR-007. |
| Approved Demo body/input readability rules | Q32 permits terminal font10–24, default14 | Apply the font range only to the terminal emulator; do not resize/retheme existing coordination pages. |
| Existing retained business history/notifications | No terminal recording; grant notices explicitly absent | Separate safe connection/mapping/security audit; no terminal bytes and no grant notifications. Existing Usage History/in-app notices unchanged. |

The amendment is requirement-supported but this **design and exact integration
plan still await PR review**. Old wording remains as historical MVP scope and is
not silently deleted. Phase A changes only Markdown; deployment/feature flags are
not actually added/enabled.

## Open engineering/security gates

| ID | Conflict / missing proof | Required resolution and blocking scope |
| --- | --- | --- |
| C1 — **RESOLVED AS SCOPE REVISION 2026-11-05** | Earlier design sought to prevent an authorized UART user from invoking tmux commands or entering Console Client shell. The owner instead explicitly authorizes full interactive shell privileges of the preconfigured SSH account after tmux Detach, including native tmux controls. Mock tests that demonstrated tmux escape from ForceCommand thus exposed a false security assumption, not a remaining forbidden operation. | Remove strict tmux command isolation/forced-command as a requirement. Gateway must auto-attach **only an existing** configured session (never auto-create/kill), keep user in interactive SSH shell after Detach, use fixed Client identity and preserve auth, host-key, audit, session revocation, and no port-forward/API target injection. Explicitly accept cross-SUT Linux-account reach and limited per-command attribution. **C1 authorization interpretation closed; live SSH behavior still unimplemented and untested.** |
| C2 — **RESOLVED BY OWNER 2026-11-05** | Initial Q5 wording allowed any syntactically valid IPv4 without Lab CIDR list; the owner now explicitly chooses **RFC1918 private IPv4 only, no Lab-specific CIDR allowlist**. | Enforce 10/8, 172.16/12, 192.168/16 and still deny sensitive self/host/metadata/control-plane targets within private ranges. Reject all non-RFC1918/public BMC endpoints. Update security, contracts and acceptance tests. **C2 interpretation closed; implementation and network-pilot tests still pending.** |
| C3 — **OPEN TOPOLOGY/PILOT GATE** | Fixed Client SSH identity must access existing tmux owner/socket, share writable attachments, and permit interactive shell fallback on Detach. Existing session owner, socket path, shell startup permissions and Console Client Linux-account privilege scope are not verified. | Use a reviewed representative disposable Client to prove login + exact existing-session auto-attach + Detach-to-shell + multiple writers + disconnect without gateway-induced session kill. Specify the remote account's Linux permissions and limits, authentication method and socket access; **do not require a forced-command escape sandbox**. No production Client changes without authorization. **Blocks live UART pilot, not mock-only design.** |
| C4 | HTTP/WS is owner-approved yet exposes reusable Client provisioning credential, BMC password, cookie and console data | No technical contradiction can make plaintext confidential. Operator acknowledgement, bind/firewall/egress and credential sensitivity review required for deployment. Do not reclassify HTTP as safe or require unapproved corporate DNS/certificate. **Blocks production enablement**, not offline design. |
| C5 | RD can replace a shared Client host key and affect other users; OOB fingerprint source is unspecified | Document independent trusted fingerprint distribution and authorized RD training/incident path. Malicious trusted RD can still poison trust; audit is detection, not prevention. Owner/security must accept residual risk. **Blocks trust pilot acceptance**. |

C1 and C2 now have explicit later owner decisions (C1 interactive shell 2026-11-05; C2 RFC1918 IPv4 2026-11-05). C3 remains a live-topology gate; C4/C5 remain risk reviews. These review records do not authorize live network connections or deployment. Not
an invitation to rewrite the83 decisions or make real network connections.

## Engineering assumptions (proposed, not confirmed business policy)

| ID | Default proposed for review | Consequence / readiness |
| --- | --- | --- |
| A1 | Q84 revoke UX: Admin confirm, then immediate revoke and re-evaluate other rights | Q77 already allows revoke; confirmation UX remains unconfirmed, no extra notification. |
| A2 | tmux grammar ASCII64 chars, no dots/colons/leading dash/metacharacters; exact target | May reject legitimate existing names. Verify inventory compatibility out of band before C; revise grammar with safe literal command construction if needed. |
| A3 | One web authorizer + separate non-root private broker, single SQLite writer; Unix socket and per-boot mutual auth | Requires later reviewed packaging/egress/UID design; not deployment changes in A. Compromised authorizer remains privileged. |
| A4 | AES-GCM envelope encryption; identity-preserving KEK rewrap does not revoke sessions, SSH credential replacement does | Crypto/library/key lifecycle review before B/C. Compromise triggers explicit global Console fencing. |
| A5 |3 transient retries1/2/4s;15s heartbeat/45s lost-peer lease;30s quota/ticket reservation;2s output authorization lease;2 concurrent BMC auth/user,16 total SSH auth including Admin validation | Fixed10 total sessions,10s connect and3 credential attempts are owner rules; these other budgets are engineering and need load/crash tests. No idle cutoff or cross-flow lockout. |
| A6 | Archived mapping/history may be edited/cleared by active RD; inactive slot; archive cannot Connect. Conflicting restore returns409 | Avoid permanently occupying active pair or silently stealing another SUT's mapping; consistent exception must be reviewed with existing archive UI. |
| A7 | If writer authority disappears, downgrade to RO when shared_readonly still permits it; otherwise close | Requirement explicitly says terminate when no other auth; mode re-evaluation avoids unnecessary disconnect while maintaining per-input deny. Endpoint/trust revocations always close. |
| A8 | Session login digest is historical indexed value without FK to pruned LoginSession | Existing logout/reset deletion must still work; live lookup remains mandatory, no dangling-auth authorization. |
| A9 | Strong maintained SSH algorithms only; no automatic SHA1/DSA downgrade | Legacy BMC compatibility may need separate security approval; do not silently broaden algorithms. |
| A10 | Keep mapping/trust/grant/Console audit histories; lifecycle metadata retention/old ciphertext disposal requires approved policy | No terminal recording; no new purge of indefinite existing Usage History. Backup key IDs must remain recoverable. |
| A11 | REST/frame/queue/paste/resize/scrollback byte limits as contracts; safe OSC/link behavior | Need Chromium and throughput testing; user-approved10k lines and14px/10–24 controls remain fixed. |
| A12 | Extension API accepts an explicit later UTC expiry bounded by original24h; UI offers clearly labelled presets | Exact extension form not owner-decided; no silent clamping/renewal. |

## Reconciliation of the existing remote draft

Initial push was rejected non-fast-forward because `06d23f8` already contained a
Phase A proposal on the same base. This branch normally merges that commit with
`8f6cabb`; neither history is rewritten. The83 owner decisions remain unchanged.
The following **engineering alternatives** were present in that draft and are
preserved for explicit review rather than silently promoted to owner policy:

| Prior item | Consolidated treatment |
| --- | --- |
| H1 helper confinement / no-start-server | Historical strict helper/escape confinement is superseded by owner-approved interactive Client shell. Retain Gateway-only automatic existing-session attach, no auto-kill/create, scoped Gateway entry and ongoing auth; C3 validates actual Client tmux/socket/shell topology. |
| D1 public-target ambiguity | **Resolved** by 2026-11-05 owner decision: private RFC1918 only, no per-Lab CIDR allowlist. Historical alternatives are recorded here, not active implementation options. |
| H2 disabled Client retains binding's unique slot | **A14:** alternative to this package's proposed inactive slot while Client disabled. Q21 says disabled bindings free active slots; whether that includes Client disable must be explicitly settled before B schema/trigger semantics. Keep mappings/history in both cases, no silent stealing or revival. |
| H3 unconfirmed early-revoke UX | A1 retains proposed confirmation only; Q84 is not owner-confirmed. |
| H4 tmux max128 vs proposed64 | A2 retains both as compatibility choices; grammar/safe exact encoding needs review before validator/schema is frozen. No remote renaming. |
| H5 broker same UID10001 vs proposed separate UID10002 | A3 retains same-image/private broker option and distinct-UID least-privilege recommendation for review; existing web UID10001 is fixed. Neither alternative changes deployment in A. |
| H6 proof60s/lease1s and previous frame/resize/rate budgets | A5/A11 are proposals, not fixed owner values. Current contracts recommend proof120s/lease2s and smaller message budgets; benchmark/review before C. Exact login/grant expiry caps and immediate revocation fencing apply whichever values are chosen. |
| H7 metadata retention | A10 retains no purge of business history; Console metadata/ciphertext disposal remains reviewable. |
| H8 remote BMC shell privileges | **A13:** app supplies no power/firmware automation; full interactive SSH cannot enforce a universal typed-command/pivot ban. Review this interpretation before BMC live rollout; if owner expects command confinement, resolve design rather than claim enforcement. |
| Earlier REST/WS routes/protocol and migration placeholder | **A15:** names were never implemented. Consolidated contracts use `sut-console.v1` and the resource paths in contracts.md; proposed migration console001_b01 remains unreserved. Prior `console.v1`/console001_foundation names are historical alternatives, not additional API aliases or two competing migrations. |

The numerical/protocol recommendations are consolidated to avoid two active
specifications. A13–A15, as with A1–A12, remain proposals requiring review. Existing
root-document change-control guidance is retained. Old schema.md/validation.md
links remain valid entry points to the consolidated documents.

## Phase B readiness

Ready to review additive schema/services contracts and mock-only security invariants.
Before starting B: approve this scope amendment, choose crypto/library/schema details
(A2/A3/A4/A8/A14), confirm no hidden current-head migration conflict, and commit fixture
plans. C3/C5 are tracked blockers before live connector/trust rollout; C1/C2 are scope-resolved but remain unimplemented and untested, and they do
not justify missing foundational tests or declaring production-ready. Phase A
review is not owner acceptance of assumptions merely because they are documented.
No instruction here authorizes a pilot, Docker release, real SSH or secret rotation.
