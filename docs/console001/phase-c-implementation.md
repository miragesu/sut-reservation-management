# CONSOLE-001 Phase C — SSH Broker and WebSocket Gateway

Implementation for review, based on main `c54948a`; see
[executed verification](phase-c-verification.md). Owner Q1–Q83, approved C1/C2 and
BR-001–BR-028 are unchanged. This authorization supersedes historical Phase B
“no live connector” wording for this milestone only. Console remains OFF in all
operator Compose/install defaults. No Phase D UI or Phase E deployment is included.

## Components and trust boundary

`app.console_broker` is an independently launched process, non-root UID10002,
separate from Gateway UID10001. It rejects root/same-as-web UID at CLI startup.
It has no TCP listener, SQLite connection, database mount or remote-execution API.
Only Broker mounts the independent0600 KEK keyring. Web reads encrypted envelopes
from SQLite and a distinct32-byte IPC capability; it cannot decrypt saved secrets.
New Admin uploads and BMC authentication necessarily traverse web RAM/private IPC;
neither existing Client secrets nor BMC credentials have a reveal response.

Unix IPC v1 has a196608-byte bound, signed canonical JSON, HMAC-SHA256, random
nonces, short request deadlines, replay rejection and Broker-boot binding. Both
peers verify Linux SO_PEERCRED. The Broker-owned directory is0750 (2750 for a
shared group10001), socket0660, capability0640 Broker:10001; KEK directory0700,
keyring0600 Broker:Broker. Only explicitly allowed operations are dispatched.
Authenticated web code is a trusted authorization/record resolver, not an untrusted
client: compromise of that process can abuse its private Broker capability. This
does not provide isolation against root or the shared remote account's privileges.

The image contains both identities, root-owned readable application code and the
normal UID10001 entrypoint. Merely building it does not launch Broker. Production
Compose, setup.sh, ports and feature flags are unchanged. Runtime separation must
use read-only images and separate mounts; never mount KEK into web, SQLite into
Broker, or the Docker socket into either.

## SSH and credential lifecycle

AsyncSSH2.23.1 with the bcrypt extra supports password and passphrase-encrypted
OpenSSH private keys without temp files/agents. WebSocket support is explicitly
locked via websockets15. Credentials and errors are never logged; AsyncSSH logging
is disabled. SSH config/agent/GSS/hostbased/kbdint/X11/proxy/forwarding features are
not exposed. Modern explicit algorithm lists exclude SHA1 host signatures/CBC.

Host discovery deliberately rejects every key before user authentication. User
acceptance requires exact fingerprint, current version, independent-verification
attestation and exact impacted-generation confirmation. This attestation records a
human assertion, not cryptographic proof of OOB verification. Authenticated SSH
requires the exact pinned public key and server possession verification first.
No automatic TOFU, accept-all policy or disabling known-host verification is used.

`client-validations` does auth only, then Broker returns an encrypted candidate.
Its RAM-only ID is actor/login/version/connection-epoch/trust-bound for120s and is
consumed on commit. Name/IP/Lab checks and impact proofs are rechecked in the final
transaction. Failed auth leaves old credentials, mappings and attachments intact;
changed candidate trust is not committed ahead of successful auth. Initial Client
trust is Admin-only; existing endpoint trust follows the approved RD authority.
Client trust replacement closes Client-wide UART attachments; BMC replacement
closes only that SUT's BMC attachments. History/audit remains append-only.

BMC targets are canonical RFC1918 IPv4, fixed22, with self/interface/broadcast,
route-gateway, metadata and configured sensitive destinations denied independently
by Gateway and Broker. No per-Lab CIDR allowlist. User enters credentials for each
flow; at most3 attempts/120s, no rolling account lockout. Credentials live in the
current request/task only and are cleared on completion/cancellation. Python cannot
guarantee physical memory zeroization. Fresh/retried BMC connection prompts again.

## UART prerequisite and native shell

The configured SSH account must already have access to its **default tmux socket**
and an exact existing session name matching the approved syntax. Gateway executes
only `tmux -N has-session -t =NAME`, exact `attach-session`, an internal random
readiness marker, and an ordinary interactive `$SHELL` after successful Detach.
A missing session exits44 without shell or session creation. No automatic tmux or
minicom creation, kill, restart, rename, option setting or repair occurs.

Native keybindings and multiple simultaneous writers are intentionally permitted.
After Detach, the RD has the ordinary fixed account's Linux authority, including
commands and native tmux operations. **No per-SUT OS confinement is claimed.**
Normal close closes its SSH connection only, not a remote process/session signal.
A different-owner/custom-socket topology is not automatically supported or repaired;
C3 account/socket permissions and preexisting minicom remain operator prerequisites.

Read mode attaches tmux with `-r` and rejects input independently in both processes.
A read-only UART attachment remains read-only even if application rights increase;
server emits `reconnect_required` and a fresh explicit connection is required to
obtain a writable tmux client. No remote tmux reconfiguration implements promotion.
A writable attachment downgraded by policy is immediately blocked by Broker input
mode as well as fresh Gateway checks. C1 confinement is not reintroduced.

## Gateway contracts

Existing Phase B mapping/grant/history/read APIs remain. Phase C live routes are
registered only when Console is explicitly enabled and a Broker socket configured:

| Route | Current contract |
| --- | --- |
| POST `/api/v1/console/client-validations` | Admin candidate fields/optional existing ID+version+new secret; returns challenge or120s validation_id; actual auth-only Broker check |
| POST `/api/v1/console/clients` | `validation_id` only; candidate contains exact validated metadata; direct unvalidated legacy payload is refused |
| PATCH `/api/v1/console/clients/{id}` | Phase B metadata fields; connection/secret changes use validation_id, expected_version and exact impact confirmation from `/preview` |
| POST `/api/v1/console/trust/challenges` | Exactly one existing client_id or sut_id; explicit SSH discovery, fingerprint/old pin/version/impact |
| POST `/api/v1/console/trust/accept` | challenge_id, expected_trust_revision, exact fingerprint, out_of_band_verified=true, confirmation_id when impacted |
| POST `/api/v1/console/sessions` | sut_id, transport, expected_revision, tab_id; reserve one of10 slots and return one-use ticket, generation, expiry, mode and HTTP warning |
| POST `/api/v1/console/sessions/{id}/attach` | Same owner/login/tab, attachment_generation, confirm_connected; fresh ticket/generation in same logical slot |
| WS `/ws/console/v1/sessions/{id}` | Cookie+exact Origin, `sut-console.v1`; no query string; first hello within3s redeems ticket and tab/generation before any output |

The executable DTOs are `schemas/console_live.py`. First frame:

```json
{"v":1,"type":"hello","ticket":"ephemeral","tab_id":"tab","attachment_generation":1,"cols":100,"rows":30}
```

Client frames: input(base64,seq,generation), send_key(esc/tab/ctrl_c/ctrl_d/ctrl_z),
resize, authenticate(flow_id,username,password; BMC only), disconnect, paste_begin
and paste_chunk. No host/port/account selector, arbitrary command, forwarding or
SFTP frame exists. Output is binary; control messages are JSON. `input_ack` means
`broker_written`, never execution/UART delivery/device success. State, connected,
participants, auth_required, input_rejected, revoked and reconnect_required use
safe reason codes; no raw SSH exception/stderr or terminal transcript API.

## Authorization, fencing and restarts

Single web worker remains required. Every ticket, attachment, pump and input
rechecks active login/password-change/account status, SUT policy/Claim/grant,
mapping/Client/credential/trust epochs. Ten logical slots are shared across UART
and BMC; retries preserve one slot and increment generation. No keyboard-idle cutoff.
Participant display is authenticated, distinct by user ID, not a transcript.

A local async authorization barrier serializes commit/fence decisions, not writers.
Short SQLite units end before IPC awaits. Existing live Broker attachments are
paused before HTTP mutations; after commit, valid links resume and invalid links
are fenced/closed. An unrelated pending SSH attempt is not cancelled: it has no
Gateway input/output authority until a fresh post-open check; affected pending
attempts are cancelled through generation-specific outbox fences after commit.
Background changes are also checked before input and every100ms pump iteration.
Broker independently refuses expired/fenced/read-only input with <=2s leases capped
by login/grant expiry. A dead/unresponsive Gateway cannot renew them.

Revocation delivery is marked only after exact generation fence **and** close ACK.
IPC failure before mutation denies it; failure after commit returns the actual
committed response with `X-Console-Revocation: pending`, never a false rollback or
false delivery. Durable pending rows are reconciled after recovery. Old closes
cannot release a replacement generation's quota slot.

SSH establish is bounded10s; transient UART retries are finite at1/2/4s. BMC
transient reconnect uses the same bounded backoff but requires fresh credentials.
No terminal input is buffered for replay. Deliberate Disconnect, mapping/trust
change or authorization revocation never autoreconnects. Network loss ends its
attachment; explicit Connect obtains a fresh ticket. Broker boot changes fail old
links closed; only a new authenticated Connect can bind its new incarnation,
fence/close stale metadata and allocate a fresh attachment. Gateway restart also
closes old metadata rather than resurrecting it.

## Resource budgets and security limits

Provisional engineering settings (not new owner decisions): WS16KiB frames,
64frames/s and32KiB/s with bounded bursts;8KiB writes;64KiB atomic checked paste
including hash, newline confirmation and control/NUL rejection;30s paste assembly.
Broker128 live/pending sessions,16 global/2 per-user concurrent SSH authentications;
32 private IPC handlers;32 Gateway hellos; output128×8KiB per attachment with2s
backpressure close; input/output send deadlines2s. Challenges256/candidates128,
120s TTL. Review A1–A15 before production sizing; limits are not writer exclusivity.

HTTP/WS remains forbidden unless `CONSOLE_ALLOW_INSECURE_HTTP=true`; the operator
accepts plaintext cookies, BMC/Admin uploads and terminal traffic on that browser
hop. Restrict ingress to the reviewed intranet, do not port-forward publicly,
protect shared workstations and use VPN/segmentation where approved. HTTPS/WSS
uses the same exact-Origin and cookie controls; trusted TLS/proxy configuration
still needs an independently reviewed rollout. HTTP opt-in is not encryption.

## Mock deployment recipe and remaining gates

Do not copy the mock's sshd/password provisioning to production. Reproduce with:

```sh
docker build -t sut-console001-c:local .
python scripts/console_mock_smoke.py
```

Managed proxy environments pass `--secret id=build_ca,src=...` for the first build
and `SUT_BUILD_CA=...` for the harness; never disable TLS. Harness creates only an
internal Docker network, transient credentials and its own named volumes. It
checks UID10001/10002, disjoint DB/KEK mounts, real HTTP/WS/SSH and cleans up.
Application CI runs the harness after its ordinary local image build; no publication.

No schema change was necessary: Alembic head remains `console001_b01`; encrypted
credential/session/epoch/outbox tables are the merged Phase B schema. Keep encrypted
DB backups and separately protected, versioned keyring backups; loss of all matching
KEKs means old Client credentials cannot be recovered and must be re-entered.
Retain old KEKs until every retained credential/history/backup is rewrapped or
retired under a reviewed maintenance procedure. No online decrypt/reveal or
production key-rotation deployment is added by this milestone.

Phase D may consume these DTOs only after this branch is reviewed; it is **not
started or automatically authorized**. C3 actual account/socket/sshd topology,
C4 plaintext exposure acceptance, C5 independent host fingerprints, real BMC SSH
compatibility, remote account privileges, key backup/rotation and operational
recovery/load review remain production gates. Shared SSH identity limits remote
command attribution; audit identifies web attachment/account/mapping events only.

### Explicit future opt-in configuration (not production deployment)

Gateway settings added by this branch are `CONSOLE_BROKER_SOCKET`,
`CONSOLE_BROKER_IPC_KEY_FILE`, `CONSOLE_BROKER_UID` (10002), and
`CONSOLE_ALLOWED_ORIGINS` (JSON array, exact scheme/host/port, additionally checked
against request Host). Keep existing defaults until an approved pilot. An isolated
operator-controlled Broker invocation is:

```sh
python -m app.console_broker --socket /run/console/broker.sock \
  --ipc-key /run/console/auth --keyring /run/console-keys/keyring
```

Run it as10002 with group10001; Gateway10001 receives only the socket/capability
mount and sets corresponding paths. Provision credentials/keyring through a trusted
secret-management process, not command-line secret literals. Do not reuse login
SECRET_KEY, add KEK to `.env`, or put secrets in images/repository. Apply reviewed
control-plane/host deny addresses to both `CONSOLE_SENSITIVE_IPV4` (Gateway JSON
array) and Broker's repeated `--deny-ipv4`; automatic container-interface/gateway
classification cannot infer every sensitive address on a company LAN. Never use
real production IPs in fixtures. Normal entrypoint still migrates before starting
one web worker; Broker does not run migrations.

Cancellation cleanup is shielded from the ASGI cancellation scope, with a5s total
budget. Logical quota/flow closure precedes network reconciliation; failures retain
unacknowledged revocations and Broker leases fail closed. This addresses the
immediate-browser-close race found during the full regression run.

A container running only Broker must override/disable the application image's HTTP
healthcheck (which targets web port80). Supervise authenticated private IPC status
from Gateway readiness; do not create a public Broker health port. Mock-only images
explicitly disable the inherited web healthcheck and use their own socket/pipeline
assertions. The normal web container retains its existing port80 healthcheck.
