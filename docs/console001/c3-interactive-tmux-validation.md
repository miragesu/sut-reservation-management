# CONSOLE-001 Phase A.2 — C3 interactive SSH/tmux validation

Result: **FEASIBLE WITH PREREQUISITES** — demonstrated on the disposable topology
below on 2026-11-05. This resolves technical feasibility for that topology, **not**
production C3 approval, a deployed Console feature or authorization to start Phase B.

Base: `feature/console001-phase-a` at
`144623a53e50109119510101dc3e375210ff7f61`, fetched before this research branch.
The complete [requirements](../CONSOLE_001_REQUIREMENTS.md), including the approved
2026-11-05 UART interactive-shell amendment, govern this experiment. Q1–Q83 are
unchanged. C1 confinement is superseded: native tmux controls and the configured
Client account's ordinary Linux shell are intentional capabilities. C2 remains
resolved: RFC1918-only BMC targets, no Lab CIDR allowlist, sensitive/self denials.
No BMC connection or address-policy implementation was tested here.

## What was actually tested

The proposed browser → Gateway → SSH leg was represented by two independent
OpenSSH CLI processes on real pseudo-terminals. There was **no browser, WebSocket,
FastAPI Gateway, SSH Broker, application database, real UART, or minicom process**.
The target pane ran synthetic byte echo/counter code as the minicom/UART equivalent.
Thus the evidence proves SSH/tmux transport and lifecycle feasibility; it cannot
be reported as browser/authorization/encryption/revocation acceptance.

| Component | Tested value |
| --- | --- |
| Local Docker Engine | 28.4.0; Linux amd64; managed local Unix socket |
| Container base | Debian bookworm-slim, Debian12.15 |
| Base manifest digest | `sha256:99c0b25c46d0214d5a2091092e7908907dcaecd6a962cde0ac700acee222b6f3` |
| tmux | 3.3a; Debian package `3.3a-3` |
| OpenSSH client/server | 9.2p1; packages `1:9.2p1-2+deb12u10` |
| OpenSSL reported by ssh | 3.0.22, 25 Aug2026 |
| Fixture Python | 3.11.2; `python3=3.11.2-1+b1` (research tool, not app runtime) |
| Local research image ID | `sha256:867a62f56e6005e5be53b4c6fe97ce47df24f581f5ab4ac1451e6298e07b3a2b` |
| SSH principal | Synthetic `console`, UID/GID1000, `/bin/bash`, no sudo/root grant |
| Sessions | Pre-created `target`, `target_extra`, `other`; independent synthetic panes |
| Socket | `/home/console/socket/tmux`, `console:console`,0600; directory0700 |
| SSH | Container loopback127.0.0.1:2222; ephemeral Ed25519 identity/host keys |
| Fault injector | Container loopback2223 →2222 TCP relay, killed only for failure test |

Only this container's loopback was reachable: `--network none`, no published ports,
no host/production mounts, no Docker socket inside it. `/run/mock` was tmpfs for
keys, pins and sshd configuration. Fixture setup was container root; tmux, panes,
interactive SSH and detached shell ran as `console`. Synthetic `outsider` had a
valid test SSH key but could not traverse the owner's socket directory. No socket
permission, group, ACL or existing tmux setting was relaxed to make it connect.
The same-account owner topology is the demonstrated positive case; cross-owner
ACL/group topologies still require separate operator review and testing.

## Reproduce and inspect

From this reviewed research branch on an authorized disposable Docker host:

```sh
sh research/console001-c3/run.sh
```

[Runner and instructions](../../research/console001-c3/README.md),
[complete executable assertions](../../research/console001-c3/validate.py),
[synthetic UART](../../research/console001-c3/mock_uart.py),
[fault injector](../../research/console001-c3/relay.py), and
[sanitized actual results](../../research/console001-c3/results.jsonl) are committed.
No test credentials, host/private keys, raw terminal transcripts or databases are
committed. The output contains only versions, counters' conclusions and test status.

The runner uses these build/run operations (plus local-daemon health check):

```sh
docker --host=unix:///var/run/docker.sock build \
  --secret id=ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t console001-c3-research research/console001-c3
docker --host=unix:///var/run/docker.sock run --rm --network none \
  --hostname console001-c3-mock --tmpfs /run/mock:rw,nosuid,nodev,mode=0700 \
  --pids-limit 128 --memory 256m --cpus 1 \
  --security-opt no-new-privileges:true console001-c3-research
```

The runner clears inherited Docker endpoint selectors only, preserves registry
credentials/proxy configuration and uses writable Buildx state under `/tmp`.
HTTPS package downloads use the supplied CA as a BuildKit secret, readable by apt;
TLS verification remains enabled, and this session CA is not copied into the image.
The image base is pinned, while Debian package availability can evolve: always
retain the versions printed on rerun. This is a local test build, not an application
image deployment or Docker Hub publication.

### Exact connection startup and the Detach finding

The fixture pre-creates sessions with `tmux new-session -d` **only during setup**.
The automatic connection uses the following fixed startup shape:

```sh
ssh -F /dev/null -i /run/mock/key -p 2222 \
  -o BatchMode=yes -o IdentitiesOnly=yes \
  -o StrictHostKeyChecking=yes -o GlobalKnownHostsFile=/dev/null \
  -o UserKnownHostsFile=/run/mock/known_hosts -o ConnectTimeout=3 \
  -o ForwardAgent=no -o ForwardX11=no -o PermitLocalCommand=no \
  -o EscapeChar=none -o ClearAllForwardings=yes \
  -tt console@127.0.0.1 \
  'if tmux -N -S /home/console/socket/tmux attach-session -t =target; then exec /bin/bash -i; else exit 44; fi'
```

`TERM=xterm-256color` is supplied on the local SSH process environment. The3s timeout
is only a mock-test setting, **not** a replacement for the approved production10s
establishment budget. Session names use the proposed A2 mock grammar and are
constructed with `shlex.join` as literal argv inside a fixed template. Five
metacharacter/path/option-injection inputs are rejected before connecting. This
is a test construction, not an implemented Gateway command API.

`=target` matches exactly; `target_e` is rejected even though `target_extra` exists.
`-N` prevents starting an absent tmux server. An absent session/server returns44
without shell fallback, another-session fallback, or creation of tmux/minicom.
There is no `new-session`, `kill-session`, `switch-client`, tmux setting change,
minicom start, or diagnostic command in automatic startup.

The negative control used **plain attach without shell fallback**. Ctrl+B,d
terminated that SSH channel; this approach fails the approved Detach behavior.
The positive fixed template waits for successful tmux detach then `exec`s ordinary
`bash -i` **in the same SSH PTY**. Ctrl+B,d left SSH alive; a user command produced
`SHELL_ALIVE TERM=xterm-256color USER=console`. A subsequent user `touch` succeeded.
No login dotfile, tmux binding, server option, session or minicom setup was modified
to obtain this behavior. A nonzero attach failure does not expose fallback shell.
A future implementation must handle failures after attachment and shell termination
explicitly rather than treating every SSH exit as a successful user detach.

No ForceCommand confinement is installed or proposed. Native user Ctrl+B,: commands
successfully switched to `other`, created a shell window, and closed that user-created
window. These are **owner-approved user actions**, distinct from automatic Gateway
startup. They can affect peers on the shared server, and are not isolation failures
under the revised requirement. Production code must not filter them to reintroduce
superseded C1 confinement.

### PTY, shared access and lifecycle

Two SSH clients attached to the same target. Both received both synthetic writers'
bytes. The native tmux client resized from100×30 to132×44 via local `TIOCSWINSZ` and
SIGWINCH; no `window-size` override was applied. After Detach, `stty size` in the
shell reported37 rows ×117 columns following another resize. TERM was verified
in that SSH shell; tmux's existing pane TERM can differ natively and was not changed.
Native multi-client sizing/crop semantics remain; this is not full ANSI/browser-fit
acceptance or a promise that every existing tmux configuration behaves identically.

Closing the first SSH did not close its peer. Closing all attachments left all
three original tmux panes alive, with unchanged process IDs. Reconnect allocated
a fresh SSH client and reattached the configured target; the mock UART input byte
counter stayed unchanged until fresh input was explicitly sent, then increased
exactly once by that input's length. Old scrollback/output is not input replay.

For abrupt loss, a loopback-only relay carrying one SSH connection was terminated.
SSH returned255, the persistent sessions survived, and a fresh pinned-host SSH
attachment succeeded without replay. The harness separately knows explicit local
Disconnect intent. **Transport EOF/exit code alone cannot reliably distinguish a
user action, peer failure, network loss or revocation.** The future Gateway must
record deliberate Disconnect/revocation as nonretryable before transport teardown;
only unexpected eligible failures may enter bounded retries. No production retry,
quota, heartbeat, timeout or WebSocket state machine was implemented here.

The fixed Client credential is intentionally reusable across new connections under
Q1/Q9. In this mock it exists only within the disposable environment lifetime, with
private-key0600 and a dedicated tmpfs removed on container exit. No credentials are
replayed as terminal input. Production encrypted storage, decrypt-in-RAM handling,
rotation, failed-flow cleanup, BMC per-attempt erasure and forensic zeroization are
**not demonstrated** by these temporary-file tests. Production must follow the
separate [secret lifecycle design](security.md), not copy the fixture key-file model.

## Actual PASS/FAIL evidence

Each PASS below is one executable assertion from the committed JSONL. The
attach-only negative control passes by reproducing the documented unsuitable
behavior; the positive template is the candidate that meets Detach-to-shell.

| Check | Result | Sanitized observation |
| --- | --- | --- |
| `incorrect-key-denied` | PASS | synthetic untrusted Ed25519 key rejected |
| `incorrect-host-key-denied` | PASS | mismatched pinned host key rejected; StrictHostKeyChecking=yes |
| `missing-exact-session:missing` | PASS | exit44, no prefix match/fallback/create/delete, original pane PIDs unchanged |
| `missing-exact-session:target_e` | PASS | exit44, no prefix match/fallback/create/delete, original pane PIDs unchanged |
| `missing-server-not-created` | PASS | tmux -N failed; no missing socket/server created |
| `other-unix-account-denied` | PASS | directory0700/socket0600 deny unrelated UID; no chmod/ACL repair |
| `attach-only-negative-control` | PASS | plain attach terminates SSH after Detach; wrapper is necessary |
| `interactive-ssh-exact-attach` | PASS | two live SSH PTYs attached to exact target, not target_extra |
| `ssh-pty-resize` | PASS | SIGWINCH/TIOCSWINSZ reached remote tmux client:132x44; no window-size option change |
| `shared-concurrent-read-write` | PASS | both SSH clients received both synthetic writers; no writer lock |
| `native-session-switch-allowed` | PASS | user Ctrl+B : switch-client succeeded as explicitly approved; no per-SUT confinement |
| `native-window-create-allowed` | PASS | user-initiated native tmux new-window allowed; NOT Gateway startup |
| `native-window-close-allowed` | PASS | user removed own test window; original mock processes unchanged |
| `detach-to-ordinary-shell` | PASS | Detach leaves same SSH alive in bash -i as non-root console, TERM=xterm-256color |
| `detached-shell-pty-resize` | PASS | ordinary shell stty reports37 rows117 columns after resize |
| `linux-account-commands-allowed` | PASS | authorized user shell command ran with fixed account privilege, no sudo/root |
| `disconnect-preserves-peer` | PASS | intent=deliberate_disconnect; only local first SSH closed; peer and pane PIDs unchanged |
| `all-disconnect-preserves-mocks` | PASS | zero attachments, original three tmux sessions and mock UART processes preserved |
| `fresh-reconnect-no-replay` | PASS | fresh SSH client reattached exact target; input byte counter did not increase |
| `fresh-input-only-on-reconnect` | PASS | new explicit input counted once; no prior input queue replay |
| `relay-connection-attached` | PASS | SSH through loopback-only disposable fault injector attached |
| `abrupt-transport-loss` | PASS | intent absent; injected TCP loss yielded SSH255; persistent sessions survived |
| `reconnect-after-loss` | PASS | new pinned-key SSH attachment succeeds, no synthetic input replay |
| `gateway-forward-channel-denied` | PASS | server rejects direct-tcpip even with client forwarding safeguards removed |
| `gateway-remote-forward-denied` | PASS | server rejects remote forwarding; Gateway SSH uses ClearAllForwardings=yes |
| `sftp-subsystem-not-enabled` | PASS | no SFTP subsystem configured; interactive shell still intentionally available |
| `startup-target-injection-rejected` | PASS | five malformed target names rejected before SSH; fixed quoted startup template |
| `automatic-commands-attach-only` | PASS | every automatic startup uses existing-session attach then shell only; user inputs separate |
| `final-original-process-preservation` | PASS | original three pane processes alive with identical PIDs after lifecycle tests |
| `ephemeral-key-permissions` | PASS | keys generated only inside disposable tmpfs; never emitted, exported or committed |

Research run: **30/30 expected observations PASS**, exit0. No candidate lifecycle
failure remains in this topology; this is not all-CONSOLE acceptance.

## Production Console Client prerequisites (proposed, not deployment changes)

1. Operator selects and reviews a **non-root fixed SSH account** with an ordinary
   interactive shell. Inventory its groups, sudo/setuid access, files, tmux servers,
   minicom privileges and reachable networks. Authorize every eligible RD to use
   **that account's full effective permissions**, including other sessions reachable
   under it; reduce permissions out of band where appropriate, not by key filtering.
2. Operator supplies the existing tmux server socket path, owner, supported version
   and exact configured session name. The demonstrated path uses the session owner's
   same UID. Other-owner sockets may require separately authorized Unix permissions
   and tmux server user ACLs; do not automatically chmod/chown, add broad socket access,
   restart processes or repair the host from the Gateway. If the current configured
   identity lacks access, C3 for that deployment remains blocked.
3. Confirm tmux and shell binaries, login/startup scripts and default bindings in a
   representative disposable topology. Ordinary SSH startup must not auto-create
   sessions, `exec tmux` without fallback, or run unexpected hardware commands.
   The fixed attach→shell template needs implementation/review and error handling
   for the actual shell/SSH library; no mandatory helper installation or dotfile
   modification was proved necessary in this same-owner mock.
4. Distribute trusted SSH public host keys/fingerprints independently, provision the
   fixed credential out of band, and keep strict pin verification. Both wrong-key
   and wrong-host-key failures were tested; password-based Client auth, old servers,
   algorithm compatibility and auth-only Q70–Q72 validation remain separate tests.
5. Future Gateway accepts authorized resource IDs, resolves host/port/account/socket
   from trusted server-side records, and constructs only fixed automatic startup.
   Browser input bytes may become shell commands **after connection**, but must not
   become arbitrary SSH destination/account overrides or a generic HTTP/RPC exec API.
   This research has no browser API to prove those authorization checks against.
6. Disable Gateway-requested TCP/agent/X11/tunnel forwarding and local SSH escape/
   command features. The mock also disables forwarding and SFTP server-side. Review
   actual Client SSH policy before a pilot; do not change a production sshd here.
   An authorized remote shell can run networking/file-transfer programs with its
   account's permissions; these SSH-channel controls are not a general pivot ban.
7. Implement and independently test application authentication, all three Compose
   policies, read-only input gates,10-session quota, mapping/host-key/credential
   revocation and lease expiry. These checks must remain effective in the detached
   shell too. Closing Gateway SSH cannot promise termination of user-started remote
   background processes or reverse changes made by an authorized user.
8. Obtain explicit operator/pilot approval for account privileges, network exposure,
   shared-writer disruption, independent key custody, and HTTP plaintext risks.
   Preserve feature-off defaults and production5088→80/non-root/SQLite deployment.

## Remaining risks and unverified gates

| Area | Status / limit |
| --- | --- |
| Browser → authenticated WS Gateway → Broker | **NOT IMPLEMENTED / NOT RUN**. No end-to-end browser test, generic-exec API denial, destination/identity tampering, CSRF, Origin, ticket, policy or revocation result is claimed. |
| Remote account attribution | Multiple RD share one OS identity; OS command/process/file attribution is limited. Gateway may audit Web actor, target and lifecycle only. Q10 still prohibits terminal command/output recording. |
| Per-SUT isolation | **NOT PROVIDED / NOT REQUIRED** under the amendment. Native shell/tmux commands can affect other sessions/files and users' shared work within Linux permissions. Shared input and window changes can disrupt peers. |
| Shell process lifecycle | Disconnect preserves existing tmux/panes in these tests. User-initiated native commands may intentionally kill/change them; shell jobs may outlive a Web link. No promise of undoing user commands. |
| Real Client topology | **UNVERIFIED**: actual account, socket ownership/ACLs, shell profile, tmux version, existing minicom and external PuTTY coexistence need an independently authorized representative pilot. No production connection was made. |
| Cryptography/credential lifecycle | Key-based SSH only. Password/key GUI provisioning, encryption, rotation, auth-only probes and secret cleanup in production services are **NOT RUN**. Temporary mock keys are not a production storage design. |
| HTTP/WS and future HTTPS/WSS | Approved `CONSOLE_ALLOW_INSECURE_HTTP=false` default and explicit opt-in remain. HTTP/WS exposes cookies, provisioning credentials, BMC passwords and shell stream to interception/injection; downstream SSH does not fix this. Operator acknowledgement, trusted LAN bind/firewall, visible warning and C4 signoff required. No WS/WSS or browser transport test here. |
| Host trust / C5 | Wrong pin safely rejected in mock. RD trust UI, scope revocation and independently trustworthy real fingerprint distribution remain unverified pilot gates. |
| Existing application regression gates | pytest, application/container deployment, three Chromium suites, image-only Compose, SQLite migration/recovery, installer and production LAN checks **NOT RUN** for this research-only change. Runtime app/config/dependencies remain untouched; earlier green runs are not Console evidence. |

**C3 disposition:** technically feasible for the tested same-owner Client model,
with the production prerequisites above. No modification of the existing tmux
server configuration/bindings or synthetic UART process was needed for automatic
attach/Detach/shared input; only disposable fixture setup created sessions. It is
not proof of arbitrary existing cross-account deployments. C3's production topology
and privilege approval remain open; C1/C2 decisions are not reopened. Phase B–E,
production pilot, image publication and merging PR#13 remain outside this task.

Documentation/tool verification commands and final delivery details are recorded
with the research PR; the executable fixture and JSONL provide the reproducible
behavior evidence rather than relying on an architectural claim alone.

## Verification record

- `sh research/console001-c3/run.sh`: PASS on **two independent disposable runs**,
 30/30 observations each (same30 cases, not60 distinct tests). Each container and
 credential tmpfs was removed; no research container remains.
- Ruff0.17.0, `ruff check research/console001-c3`: PASS.
- `sh -n research/console001-c3/run.sh`: PASS.
- Local artifact check:45 relative Markdown links resolve; all3 Python sources parse;
 JSONL contains30 unique passing cases matching all30 report rows; no private-key
 blocks or DB artifacts in the harness. PASS.
- `git diff --check`: PASS. Diff against base confirms application code, dependencies,
 migrations, Docker/Compose deployment, workflow, installer, AGENTS/SPEC/PLAN and the
 owner requirements ledger are unchanged.

No full application, browser or production test result is implied by these checks.
