# CONSOLE-001 Phase E — deployment integration

Scope: independently requested isolated deployment/pre-release work, based on main
`00776f9` (merged Phase D). Q1–Q83 and approved C1/C2 are unchanged. This is not a
release or production activation. [Verification](phase-e-verification.md),
[operator runbook](operator-runbook.md), [recovery](rollback-and-recovery.md).

## Image-only process and mount boundary

Normal `compose.deploy.yaml`, setup, port5088→80, UID10001, SQLite bind,
startup Alembic and background coordination deadlines remain. Console defaults
false / claim_only / insecure HTTP false. No schema or coordination service change.

Explicit `compose.console.yaml` overlays the image-only base. `CONSOLE_IMAGE` must
be a separately reviewed immutable image reference, shared by Web, Broker and
network initializer. It does not select/publish a release or follow moving tags.
The operator downloads both YAMLs from the same reviewed revision. Existing image
locks that override only Web must not be layered after this overlay.

| Service | Runtime | Mounts and exposure |
| --- | --- | --- |
| Web |10001:10001, cap_drop ALL, no-new-privileges, read-only root| Existing writable SQLite; read-only IPC socket directory/capability and nonsecret policy. No KEK. Only published5088→80. |
| Broker |10002:10002 + supplemental10001, cap_drop ALL, no-new-privileges, read-only root| Writable private socket directory; read-only capability, KEK and policy. No SQLite, Docker socket or public port. |
| console-network | Initializes its own namespace as UID0 with only NET_ADMIN/SETUID/SETGID; then UID/GID10003 with empty supplementary groups and zero effective/permitted capabilities | Policy only, tmpfs readiness marker, no DB/KEK/IPC. No host networking, privileged mode, Docker socket or host firewall edit. Broker joins this namespace. |

The network initializer is an explicit engineering choice for review, not a new
owner decision. Privileged initialization is separate from both non-root runtimes.
Default OUTPUT/INPUT DROP is installed before flushing/rebuilding rules; no
ACCEPT-all interval. Failed initialization never becomes healthy. The keeper cannot
change rules after dropping UID/capabilities. It has no automatic restart policy;
namespace/policy changes require ordered recreation of the complete Console stack.
Docker/root compromise remains outside this isolation guarantee.

Compose waits for namespace readiness, then Broker socket reachability, then Web.
The Broker healthcheck is socket-only and sends no credentials. Web entrypoint
performs HMAC/peer-UID authenticated status and retained-envelope verification
before migrations/listening. Missing/bad IPC, invalid or wrong/missing KEKs,
network policy, Origin or HTTP attestation fail startup. Runtime Broker loss
uses existing <=2s authorization leases/fencing; it does not create fake success.
Stop order is Web→Broker→namespace; graceful shutdown closes only Gateway links.
Independent Docker automatic restarts do not implement Compose dependency order;
boot mounts and explicit full-stack supervision are operator prerequisites.

## Network controls

`CONSOLE_NETWORK_POLICY_FILE` is file-only, read-only in Web/Broker/initializer.
Its strict version1 JSON has host_ipv4, deny_cidrs and ssh_ports. Host interface
aliases, all local Docker/control-plane ranges and sensitive services must be
reviewed on the real host; the container cannot discover them reliably. This is
an exclusion policy, not a Lab allowlist. Empty/malformed policy fails closed.

Gateway classification consults that policy on save/connect; Broker independently
checks address/port immediately before every SSH socket. Namespace firewall also
blocks raw sockets to self, host inventory, sensitive prefixes, gateway/broadcast,
metadata/link-local/loopback, reserved/special ranges, IPv6 and all non-approved
TCP ports. No DNS/proxy/forwarding service is permitted by these rules. Console
Client custom ports1–65535 remain supported when operator includes the port;
BMC remains RFC1918-only/fixed22 without per-Lab CIDRs. Firewall port22 permission
does not prove a private SSH host is a BMC. Web's ordinary base bridge is not claimed
to have an OS-level outbound firewall; SSH exists only in the separated Broker.
Host ingress firewall and accurate sensitive inventory remain mandatory.

## Secrets, setup and maintenance

`python -m app.console_deployment provision --path DIR` is an explicit offline,
root, network-none one-shot on an existing empty0700 directory. It creates
Broker-owned IPC2750/socket0660, separate capability0640(10002:10001), and
keys0700/keyring0600(10002:10002). It refuses reruns/overwrites and never outputs
keys. No startup generation/fallback. KEK is independent of SECRET_KEY and the
32-byte IPC capability; authenticated Broker status checks login-key reuse.

Web preflight passes only encrypted envelopes/AAD to the new private
`verify_credential` IPC operation. It returns only verified:true, never decrypted
content; this is not a browser endpoint or reveal API. Broker never mounts DB.

Offline `app.console_keyring verify/rewrap` is custodian maintenance, not the
runtime Broker. It explicitly mounts both DB and keyring only in a stopped,
network-none one-shot. Rewrap requires an exclusive new cold backup path, refuses
active sessions/wrong schema, verifies every retained credential, and atomically
rewraps DEKs with original ciphertext/SSH generation retained. It audits key ID and
count only. Any failure rolls the DB transaction back; matching backup/key retention
is still required. No automatic downgrade, online key export or secret API.

`setup.sh` remains the coordination installer. If console.env or
compose.console.yaml is present it refuses reconciliation/upgrade before preflight
or data changes, pointing to paired upgrade/recovery. It never silently omits the
Broker/namespace, changes a Console version, or enables insecure HTTP.

## Acceptance boundary

C1 shell scope and C2 private-address policy stay resolved. Actual Client account/
socket/minicom topology C3, plaintext LAN/operator acceptance C4, and independent
Host Key process C5 remain OPEN. Synthetic evidence does not close them.
No real host/device/data, registry push/tag, image promotion, merge or next phase.
