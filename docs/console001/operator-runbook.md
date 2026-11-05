# Console operator runbook — review before any pilot

This describes a future **separately authorized** deployment. This change does not
activate production. [Evidence/categories](phase-e-verification.md),
[backup/rollback](rollback-and-recovery.md), [owner rules](../CONSOLE_001_REQUIREMENTS.md).
C3/C4/C5 remain open until independent acceptance is recorded.

## Before provisioning

Use reviewed Linux amd64 Docker Engine/Compose v2 with namespace iptables/ip6tables
support. Review image provenance and use an approved Console-capable immutable
`mirage315/sut-reservation-management@sha256:<approved-digest>` for every service.
No Console release is published by this PR; older published images must not be
assumed to contain these helpers. Obtain compose.deploy.yaml and compose.console.yaml
from the same reviewed immutable revision; inspect/verify their checksums against
the review artifact. No source checkout, Python installation or source build is
needed on the operator host. Do not use curl|bash.

Keep the existing project name, private .env/SECRET_KEY and `/data/sut-reservation-data`
bind. Verify `/data` is the intended mounted persistent filesystem, space/backups,
UID/GID10001 and0700; never create an empty replacement for missing production data.
Do not automatically migrate Named Volumes. Follow [existing deployment](../deployment.md)
for deliberate cold migration and password bootstrap.

Boot ordering must apply **before Docker restarts containers**: configure Docker's
systemd unit with `RequiresMountsFor=/data` (and any separately mounted custody
path), plus a required preflight unit that fails unless `mountpoint -q /data`
and the intended filesystem identity match. Merely ordering a Compose unit after
docker.service cannot protect auto-restarted containers. Operator must test reboot
and missing-mount behavior on an authorized host; never use `down -v`.

Review ingress firewall and bind one trusted LAN IPv4 (or loopback for an isolated
rehearsal), not 0.0.0.0/public addresses. Limit5088 to authorized internal clients.
Do not expose Broker ports, Docker API or diagnostic listeners. Inspect real host
interfaces/routes, Docker networks and management/control-plane service addresses
out of band (`ip -4 addr`, `ip -4 route`, `docker network inspect`); record all host
aliases and Docker/management prefixes in the private policy. Do not commit that
inventory. The software cannot infer every host/NAT alias from a container.

## Independent custody

An authorized custodian creates an empty private directory, e.g.
`/var/lib/sut-console`, separately from the SQLite directory and backup bundle.
In the following, IMAGE is the operator's verified immutable reference, not a tag
chosen by this document. Run an explicit one-time provisioning container:

```sh
# Run on an authorized deployment host only, after creating the empty0700 directory.
docker run --rm --network none --user 0:0 \
  --mount type=bind,src=/var/lib/sut-console,dst=/custody \
  --entrypoint python "$IMAGE" \
  -m app.console_deployment provision --path /custody
```

Never repeat against a live directory. Do not copy keys into `.env`, DB backup,
repository, logs or Web mounts. Store an independently controlled, encrypted/offline
keyring backup, keyed by image/schema/key IDs; test restoring it. IPC auth is a
separate capability, not the KEK or SECRET_KEY. Mount only the specific subpaths
shown in Compose. No Docker socket or root entrypoint for Web/Broker.

Create a private policy file under an operator0700 directory. Its content is
nonsecret infrastructure metadata; file0644 permits the three file-only container
mounts to read it while the host parent remains0700. Restrict modifications to
the trusted operator. Example structure uses documentation addresses, **not a
usable production policy**:

```json
{"version":1,"host_ipv4":["192.0.2.1"],"deny_cidrs":["198.51.100.0/24"],"ssh_ports":[22,2222]}
```

Replace with every actual host IPv4 and sensitive/Docker/control-plane CIDR.
Required deny entries do not restrict BMC to Lab subnets. Port22 is for BMC; add
only the separately approved Console Client ports. Apply policy changes by stopping
Web/Broker and recreating namespace→Broker→Web; never hot-edit and assume existing
connections or namespace rules changed. Review raw-socket negative tests in the
isolated runner before pilot.

## Explicit activation configuration

Use a separate private0600 `console.env` as the final env-file, leaving existing
.env/SECRET_KEY intact. Set the reviewed image and private paths, exact browser
Origin JSON, bind, and the three Console settings deliberately. Defaults stay:

```dotenv
CONSOLE_ENABLED=false
CONSOLE_ACCESS_POLICY=claim_only
CONSOLE_ALLOW_INSECURE_HTTP=false
```

Policies: claim_only permits holder/Admin RW; shared_readonly permits other active
RD RO; all_authenticated permits active RD RW. Named temporary maintenance grants
are independent. Mapping/history and RD Host Key authority remain independent of
Claim; do not substitute global admin-only host trust or a writer lock.

**HTTP/WS exception (C4):** only after named operator/security approval, set
CONSOLE_ENABLED=true, CONSOLE_ALLOW_INSECURE_HTTP=true and
CONSOLE_HTTP_RISK_ACK=I_ACCEPT_PLAINTEXT_CONSOLE. This attestation is explicit but
not a substitute for a separately retained approval record, reviewed LAN firewall
or independent acceptance. Set COOKIE_SECURE=false only for the approved HTTP
site and list its exact http://host:5088 Origin. The overlay requires private/loopback
IPv4 bind. No setting is silently enabled by setup.

HTTP/WS exposes reusable login cookies, tickets, BMC passwords, Admin Client
password/private-key uploads, clipboard and shell input/output to LAN interception
and active script replacement. HttpOnly, CSRF, Argon2, encrypted DB and downstream
SSH do **not** encrypt this hop. A LAN observer may gain a shared Linux shell.
Restrict workstations/network access and knowingly accept residual risk or defer
activation. Clipboard API may fail; native Ctrl+V remains the fallback.

For future HTTPS/WSS, retain exact Origins and COOKIE_SECURE=true. The JS selects
wss:// on HTTPS. Trusted TLS termination/proxy-peer configuration and real TLS/WSS
acceptance require independent testing; the ordinary entrypoint intentionally
ignores arbitrary forwarded headers. Do not claim a reverse proxy works merely by
setting X-Forwarded-Proto, and never disable Origin checking or downgrade to ws://.

After approval, the explicit command shape is:

```sh
docker compose --env-file .env --env-file console.env -p sut-reservation \
  -f compose.deploy.yaml -f compose.console.yaml config --quiet
# Pull approved references before the maintenance window; never build on the server.
docker compose --env-file .env --env-file console.env -p sut-reservation \
  -f compose.deploy.yaml -f compose.console.yaml pull
docker compose --env-file .env --env-file console.env -p sut-reservation \
  -f compose.deploy.yaml -f compose.console.yaml up -d --no-build --pull never
```

Do not layer the older Web-only image.lock override afterward. Archive image digest,
source revision, Compose checksums, policy revision and key IDs without secret values.
Verify health, Web5088→80, non-root/zero caps/no-new-privileges, disjoint DB/KEK mounts,
Alembic head, coordination deadlines, authenticated private IPC and all negative
egress cases. An unhealthy Broker is not fixed by auto-generating a new keyring.

## Actual Client prerequisites and training (C3)

- Dedicated fixed SSH identity per Client, password or passphrase-protected private
  key; operator provisions remote credentials/authorized_keys out of band.
- Review that account's groups, files, sudo/shell startup, reachable networks and
  SSH algorithm compatibility. No root SSH requirement; no agent/X11/tunnel/ProxyCommand
  or generic Gateway exec endpoint. Remote OS/network permissions remain decisive.
- Existing tmux server/session and minicom-equivalent UART process must already run.
  Current implementation uses the SSH account's **default tmux socket**, exact
  configured case-sensitive session name `[A-Za-z0-9_][A-Za-z0-9_-]{0,63}`. Review
  ownership/ACL/group permissions. Custom sockets/different owners require separate
  acceptance; never change ownership, rename or repair live sessions automatically.
- Prove exact existing attach, native detach into ordinary interactive `$SHELL`,
  two concurrent writers/RO and disconnect/reconnect without Gateway killing the
  existing sessions. Gateway never creates/kills/reconfigures tmux/minicom.
- Authorized users may operate native tmux and the account's Linux shell, including
  other sessions/files/hardware operations allowed by that account. There is no
  per-SUT OS confinement or exclusive writer; shared input can interleave. RD
  identity is recorded at Web connection level; no per-command attribution or
  terminal transcript. Do not promise remote processes cannot be changed by users.

## Host Key procedure, audit and incident response (C5)

Obtain exact algorithm/SHA256 fingerprint through an independently trusted source:
physical/management console, signed inventory distributed by a separate custodian,
or a separately authenticated administrator. On the Client's trusted local console,
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256` shows its public pin.
A key scan from the same untrusted network is discovery, not verification.

Compare target IP/port, Client or SUT identity, algorithm and old/new SHA256 values.
Creating Admin approves initial Client trust. Active RD retains approved Q6/Q7
replacement authority. Review displayed impacted SUT/RD/session counts, explicitly
acknowledge independent comparison, then confirm. Authenticate only after the exact
pin is trusted. Client replacement closes all its UART Web links; BMC replacement
closes only that SUT/BMC. No automatic reconnect, external PuTTY/tmux termination,
Claim/queue/booking change or credential reveal.

Retain protected, terminal-free audit records: actor, target, old/new fingerprints,
versions, affected scope and closure outcome. Pending closure requires Broker/
outbox reconciliation, not a claim that DB commit equals TCP close. Unexpected
key change: stop new connects, notify the independent custodian, disable Client or
Console when appropriate, investigate target/network changes before accepting.
Compromise: fence Web attachments, isolate hosts out of band, replace remote
credentials and IPC/KEK as required, preserve encrypted DB/audit/backups and review
stolen-key exposure. Rewrapping cannot undo previously stolen secrets.

**C5 residual risk:** an authorized mistaken/malicious RD can deliberately approve
an attacker's key for others. Checkbox+audit cannot cryptographically prove OOB
identity. An RFC1918 SSH server is not proof of BMC identity. Training, independently
controlled fingerprints and explicit risk signoff remain open production gates.
