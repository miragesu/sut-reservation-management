# CONSOLE-001 Phase B — backend foundation, mock-only

Base: `main` at `80b8033` (fetched2026-11-05). Branch:
`feature/console001-phase-b`. This implements **metadata/crypto foundations only**
under the [owner requirements](../CONSOLE_001_REQUIREMENTS.md) and
[Phase A closure](phase-a-closure.md). Q1–Q83 and the later C1/C2 amendments are
unchanged. There is **no SSH implementation, broker, WebSocket, xterm, terminal UI,
production connection, image publication or deployment**. Phase C is not started.

## Implemented boundary

- Strict true/false `CONSOLE_ENABLED=false`, `CONSOLE_ALLOW_INSECURE_HTTP=false`,
  exact policy enum default `claim_only`. Invalid Boolean/enum/deny-address settings
  fail validation. Console APIs404 while disabled; internal HTTP requires explicit
  opt-in. Active login, mandatory password change, CSRF and same-Origin checks
  protect enabled APIs. Existing coordination routes/UI are unchanged.
- Enabling an isolated application process requires a separate readable, regular,
  non-symlink, private-mode keyring outside the SQLite data directory; absent/wrong/permissive key configuration fails
  startup without secret reflection. Disabled deployment needs no Console key.
- Admin metadata editing: Client name/notes, enable/disable and Lab move after all
  retained bindings are cleared; optimistic versions, scoped impact confirmation,
  safe projections and audit. Names normalize trim/casefold per Lab; IPv4 uniqueness
  includes disabled Clients across Labs/ports. DB constraints are final race guards.
- RD UART/BMC settings edit authority is independent of terminal read/write authority.
  Save/clear and revisions are independent; UART binds enabled same-Lab Clients and
  an exact existing-session name, with one active Client/name pair. No SSH/tmux probe
  on mapping Save. Archive history remains readable/editable without enabling use.
- BMC accepts canonical RFC1918 IPv4 only and fixed22; it rejects public/special
  addresses, local interfaces/broadcasts, route gateways and additional operator
  sensitive deny entries. Local discovery reads ioctl and `/proc/net/route`; no DNS,
  target probe or TCP connection. Unsupported discovery fails closed. This is not
  a Lab CIDR allowlist or proof that a private SSH service is really a BMC.
- Complete three-policy predicate uses fresh user/login/Claim/grant/SUT state.
  Lab Admin retains existing all-Lab scope; there is no invented account-to-Lab
  assignment. Same-Lab applies to Client/SUT binding. Reservation/queue status is
  never a Claim. Disabled/expired/password-change/archive states deny access.
- Maintenance grants:1/2/4/8/12/24h, optional reason, independent RD grants,
  original-created-at+24h extension ceiling, stale-version checks, revoke/expiry
  audit, no cooldown for a new grant and no revival of old grant-dependent sessions.
  Re-evaluate other authority; downgrade to read-only when independently permitted.
  Return to Normal revokes grants permanently. No grant notifications or changes
  to Claim/queue/reservation/Usage History. Existing deadline worker runs metadata
  expiry/cleanup; GET stays read-only.
- Internal quota/ticket primitives: serialized numbered slots1–10 per user across
  UART/BMC, expiring reservations, session-bound hashed single-use tickets,
  Origin/login/generation/epoch checks, same-slot reconnect and stale-close CAS.
  **No public terminal allocation/redemption route or successful connection state
  is supplied.** Tests may construct synthetic connected metadata, never real links.
- Impact proofs bind actor, login, operation payload/revision and exact affected
  session IDs/generations/epochs, not counts alone. Successful edits atomically
  append history, increment only affected epochs and close affected logical
  reservations with durable outbox rows. `delivered_at` remainsNULL: no fake broker
  ACK or claim of live SSH fencing/disconnect delivery.

### Credential-dependent operations deliberately fail closed

HTTP Client create, credential/username/auth-method/IP/port replacement, and
host-trust acceptance **cannot report validation success** in Phase B. They return
503 `client_validation_unavailable` / `host_key_verification_unavailable` (after
role/security validation), with no candidate Client/secret/trust write. No test
mode flag, supplied `verified` Boolean, credential in response, TOFU bypass or
production mock-success route exists. Thus the current admin UI/API cannot onboard
an actual Console Client or expose a terminal. This is the requested pending
Phase C boundary, not a usable SSH feature.

Offline internal commit primitives accept bounded, candidate/actor/endpoint-bound,
expiring verification evidence prepared **before** a SQLite write transaction.
A synthetic validator exists **only in tests**. They test Client+encrypted
credential+host-key atomic creation, stale-proof rejection, replacement-only
credential generations and retained trust history. Live-session credential
replacement remains503 even in that primitive until Phase C supplies reviewed
confirmation/fencing. Notes/name-only edits neither probe nor bump connection epoch.
Changing Client enabled state invalidates its UART reservations, not BMC.

## Additive database migration

Revision `console001_b01`, down_revision `c2026101601`, adds13 tables:

| Table | Purpose |
| --- | --- |
| `console_clients` | Lab/name/IP/port/method/enabled metadata, security UUID and credential ref |
| `console_credentials` | Authenticated encrypted envelopes and replacement/crypto generations |
| `console_uart_mappings` | Independent UART revision/epoch and materialized active pair slot |
| `console_bmc_endpoints` | Independent BMC IPv4/revision/epoch; no credentials or configurable port |
| `console_host_keys` | Public trust records/current partial uniqueness and retained replacements |
| `console_mapping_events` | Append-only safe before/after mapping history |
| `console_audits` | Append-only allowlisted security/grant/lifecycle metadata |
| `console_grants` | Active grant uniqueness, original time bounds and retained terminal states |
| `console_sessions` | Terminal-free logical session/quota/authority/epoch metadata |
| `console_tickets` | Hashed one-use, bounded Origin/login/session/epoch bindings |
| `console_confirmations` | Hashed impact proofs; no raw bearer or secret candidate persistence |
| `console_auth_flows` | Bounded future authentication-attempt metadata only, no credentials |
| `console_revocations` | Idempotent per-generation pending delivery outbox |

New retained entity FKs RESTRICT deletion; historical login digests intentionally
have **no FK to deletable LoginSession**. New triggers guard same-Lab writes,
credential-owner references, active-slot consistency, Client/SUT Lab changes,
archive/disable slot propagation, immutable grant creation, append-only history
and immutable/retained host-key identities. Reenable/restore collisions roll back
rather than steal a binding. No existing table is rebuilt, inventory BMC data
imported, user hash changed, Claim reassigned, or old history removed.

The revision is frozen DDL/trigger SQL, not runtime `create_all`. Empty Console
schemas can reverse to the prior revision; **any Console data blocks destructive
downgrade**. Restore a matching pre-upgrade backup/image instead. A SQL snapshot
test populates every existing business table, cold-copies its compatible prior
schema, upgrades, compares all old rows byte-for-value, checks all13 new tables
empty, and checks SQLite integrity/FKs. It restores the prior backup into a
separate empty directory and confirms the prior schema and records. This is
synthetic SQLite recovery, not an old production-image or real-server rollback.

## Encryption and key custody

`cryptography46.0.7` is the only added dependency; all existing locked package
versions are retained, with SHA256-locked production/dev requirements.
`EnvelopeCipher` uses maintained AES-256-GCM: random32-byte per-credential DEK,
independent random12-byte data/wrap nonces, an independent operator KEK and key ID,
and versioned AAD binding Client UUID, credential UUID, method and SSH generation.
Wrong/missing keys, swapped AAD and modified ciphertext fail closed with generic
errors. Rewrap changes wrapped DEK/crypto revision without changing SSH generation
or ciphertext. Key IDs and safe metadata may be audited; keys, envelopes and
saved secrets have no reveal/export API. SSH username is Admin-only metadata;
RD projections omit it as well as all credential material.

Keyring shape for isolated test configuration is
`{"active_key_id":"<id>","keys":{"<id>":"<base64 of independently generated32 bytes>"}}`.
Those placeholders are deliberately invalid keys. Tests generate ephemeral keys;
do not copy application SECRET_KEY or create production secrets for this task.
Store real future keyrings outside the repository and SQLite backup; retain
independent protected offline copies and older IDs needed by old backups.
`.gitignore`/`.dockerignore` exclude keyrings/private key files. No key generation
or replacement occurs on startup failure.

This is an **in-process foundation abstraction**, not Phase C's privilege-separated
broker. Startup only validates its key file; no production credential-provisioning
path is enabled. Actual broker custody/IPC, password/key parsing/authentication,
private-key passphrase handling, secure memory cleanup, rotation operations and
end-to-end recovery need separate review/tests. Python immutable objects do not
promise forensic zeroization. No cryptographic external audit is claimed.

## Provisional A1–A15 implementation choices

These are engineering defaults for review, **not additional owner decisions**.

| Assumption | Phase B treatment |
| --- | --- |
| A1 | Backend revoke requires Admin + expected revision and acts immediately; no new grant-revoke UI/confirmation policy is invented. |
| A2 | Temporary64-character ASCII tmux grammar `[A-Za-z0-9_][A-Za-z0-9_-]{0,63}`; case-sensitive. Review real inventory before C; no renaming or live probe. |
| A3 | Short SQLite units only; no broker/IPC or live transport. In-process crypto foundation cannot establish privilege separation. |
| A4 | AES-GCM envelope/AAD and identity-preserving rewrap primitives tested; operational rotation and custody review remain. |
| A5 | Reservation/ticket30s, impact proof120s; cap at login/grant expiry. Metadata sweeps reuse existing worker. No heartbeat/backoff/auth concurrency runtime implemented. |
| A6 | Retained archived settings/history may be edited/read; terminal authorization denied and active slot inactive. Restore collision rejects atomically. |
| A7 | Grant loss re-evaluates independent Claim/Admin/policy; read-only downgrade when allowed, otherwise logical close/outbox. Live byte fencing remains C. |
| A8 | Indexed historical login digest has no FK to pruned login rows; every authorization re-resolves active login. |
| A9 | SSH algorithm negotiation/legacy compatibility deferred; no SSH dependency/connection is added. Synthetic Ed25519 trust evidence only. |
| A10 | Keep Console/history/old ciphertext metadata; no retention purge or existing Usage History deletion. Key/ciphertext disposal policy remains reviewable. |
| A11 | Bounded typed metadata/secret fields and pagination; no terminal/frame/clipboard/output budgets implemented or claimed. |
| A12 | Extension uses explicit timezone-aware later expiry, bounded by original24h; no silent clamping/automatic renewal. |
| A13 | Accepted interactive Client/BMC account capabilities unchanged; no shell/power automation, confinement or live connection added. |
| A14 | Disabled Client frees materialized active slots while preserving mappings. Reenable/restore conflict refuses with rollback; this interpretation remains provisional. |
| A15 | Actual B route subset below; proposed terminal/WS protocol remains unimplemented. Client metadata operations share PATCH rather than inventing additional aliases. |

`console_confirmations` and separate append-only `console_audits` are additive
engineering choices: they bind racing previews without storing terminal or secret
payloads and avoid handing secret-bearing models to the generic legacy audit helper.
Key file/deny-entry configuration fields are operator controls, not Lab Admin global
config privileges. SQLite julianday supplies a defensive grant-duration check;
services enforce exact timezone-aware microsecond bounds. No remote owner topology
or production constraints are inferred from synthetic tests.

## Implemented HTTP surface

All paths start `/api/v1/console`; every path remains404 with Console disabled.

| Method/path | Phase B behavior |
| --- | --- |
| GET `/clients` | Active RD enabled safe choices; Admin may include disabled, pagination |
| POST `/clients`, `/client-validations` | Admin-only validation-unavailable503; no candidate persisted |
| PATCH `/clients/{id}` | Admin metadata/version change; validated endpoint/credential fields503 |
| POST `/clients/{id}/preview` | Exact impact confirmation for metadata disable/change |
| GET `/suts/{id}/connections` | UART/BMC safe settings, separate versions, effective policy; `terminal_available=false` |
| POST `/suts/{id}/uart/preview`, `/suts/{id}/bmc/preview` | Authorized RD preview, no remote probe |
| PUT `/suts/{id}/uart`, `/suts/{id}/bmc` | Separate save/clear, optional reason, CAS, confirmation, history/epochs/outbox |
| GET `/suts/{id}/history` | Paginated retained safe history, no restore |
| POST `/trust/accept` | Active RD verification-unavailable503; no key accepted |
| POST `/suts/{id}/grants` | Admin-only prescribed duration creation |
| PATCH `/grants/{id}` | Admin-only bounded extension and revision |
| POST `/grants/{id}/revoke` | Admin-only revision-checked revoke |
| GET `/suts/{id}/my-grant` | Own retained grants/effective timestamps only |
| GET `/sessions/me` | Own terminal-free reservation list/count; no other-tab kill |

There is **no** POST `/sessions`, WebSocket endpoint, terminal input, raw exec,
forwarding or credential-reveal route. Internal quota/ticket helpers are exercised
only with synthetic verified fixtures. Existing Compose/installer files are
unchanged and do not pass the new feature flags/key mounts yet; no deployment
instruction enables them. They stay off by default in current operator images.

## Verification and reproducible commands

Run in a disposable environment with Python3.12 and the locked test dependencies:

```sh
pip install --require-hashes -r backend/requirements-dev.txt
ruff check backend scripts
pytest -q
python scripts/browser_smoke.py
python scripts/browser_day2.py
python scripts/browser_day3.py
```

Migration tests use temporary paths only. For a manual isolated migration check,
set DATABASE_URL to a newly created temporary SQLite path, then run
`alembic -c backend/alembic.ini upgrade head` and `alembic ... check`; never point
these research commands at production. The Console fixtures exercise metadata
using synthetic accounts/keys and a test-only validator; no network authentication
is represented as passing.

Final command counts/results and deployment boundaries are recorded in
[Phase B verification](phase-b-verification.md).

## Phase C readiness and remaining risks

Ready for review of mock-only foundations, not automatic Phase C execution.
Actual SSH validation, host-key challenges/OOB acceptance, candidate single-use
proof issuance, SSH/Broker/WS authentication, input/output fencing, outbox delivery,
quota leases on real sockets and read-only enforcement must be implemented and
adversarially tested separately. A `delivered_at=NULL` record is not a disconnected
TCP session. A DB commit cannot revoke already delivered bytes.

The approved C1 interactive fixed-account shell exposes its full reachable OS
privileges and limited RD attribution; do not reintroduce per-SUT confinement.
C2 stays RFC1918-only without a Lab allowlist, with residual private-target/pivot
risk. Actual host aliases, broadcasts/routes, sensitive control-plane inventory,
Client account/socket topology (C3) and independently trustworthy host fingerprints
(C5) remain operator/pilot gates. The API address classifier is not an egress
firewall or authentication proof.

HTTP/WS plaintext interception/injection risk (C4) remains despite downstream SSH
and encrypted SQLite credentials: explicit opt-in, trusted LAN bind/firewall,
warning and operator signoff remain necessary. No WS/WSS/browser transport test is
claimed. Neither encryption nor this PR is a production safety or release approval.
No company host, production SQLite, credentials, tmux/minicom or Docker Hub image
was modified; no PR merge is authorized here.
