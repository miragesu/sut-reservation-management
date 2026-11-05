# Security threat model and deployment exception

This is a privileged debug gateway, not just status UI. Approved risk choices are
not assertions of safety. Scope conflicts/open gates are in [compatibility](compatibility.md).
Implementation and production verification are **not performed** in Phase A.

## Assets, principals and attack paths

Protect Client fixed credentials/root keys; login sessions; target identity and
mappings; authorization/grants; BMC ephemeral credentials; live terminal data and
existing business SQLite history. Adversaries include unauthenticated cross-site
pages, on-LAN observers/active MITM, malicious active RD, compromised BMC/Client,
misconfigured operator, and compromised web/broker/host. Trust in RD host-key
approval does not make RD an infrastructure administrator or trustworthy target
classifier. A compromised host/root defeats local process separation and key files.

| Threat | Proposed control / residual risk | Gate |
| --- | --- | --- |
| HTTP/WS interception/injection | Explicit operator opt-in, LAN bind/firewall, warning; no URL/log/storage secrets. Still plaintext credentials/cookies/commands and replaceable JS; SSH downstream does not protect this hop. | E HTTP risk signoff |
| Cross-site WS hijack | Exact normalized Origin allowlist, active server session, POST-CSRF-issued one-use ticket, first-frame redemption, no wildcard/null Origin. SameSite alone is insufficient. | C/D forged-origin/replay tests |
| RD chooses SSH service rather than BMC | Strict IPv4/port, special/self-target denial, broker egress firewall, pinned key and OOB identity; no Lab CIDR allowlist. Any reachable permitted SSH host can still be misrepresented as BMC. Public-address ambiguity is C2, not silently decided. | C2 + E egress approval |
| RD poisons Client host trust | Deliberate OOB comparison, old/new SHA256 fingerprint and impact warning, CAS/versioned audit and scoped live revocation. RD can authorize an attacker's key if dishonest/mistaken; no cryptographic OOB guarantee. | C trust tests / owner residual-risk review |
| tmux prefix/socket/shell escape | Restricted SSH account/helper and dedicated socket ACL; fixed command builder, no generic Client shell/forwarding. Normal writable tmux attach alone does NOT prove confinement. | C1 attach-only sandbox proof |
| Stale link writes after remap/revoke | Durable epochs/outbox, precommit barrier, per-input policy/epoch check and short broker lease. Never claim already-delivered bytes can be recalled. | C deterministic race/crash tests |
| Exfiltration via remote output | xterm text/ANSI only; disable OSC52 clipboard writes, file/download/link execution handlers; sanitize participants/error HTML. Terminal output itself can contain sensitive remote data and remains in browser RAM. | D hostile ANSI fixtures |
| Credential/terminal recording by infrastructure | Body/frame/SSH debug logging off; allowlisted errors; no APM replay/body capture, core dumps, shell history for gateway commands, temp key files or automatic downloads. Browser memory and remote-side logs remain outside erasure guarantees. | C/D canary audit tests |
| Memory/CPU/connection exhaustion |10 logical sessions/user, bounded auth concurrency, frame/output budgets/backpressure, connect timeout and finite retries. No keyboard-idle expiry or new cross-flow password lockout. | C/D pressure tests |

## Console Client encryption and lifecycle

Propose maintained authenticated encryption (e.g. reviewed cryptography AES-256-GCM),
not reversible obfuscation or a homegrown cipher. Per-credential random32-byte DEK,
unique random12-byte data nonce; wrap DEK with independent operator KEK/key ID and
separate nonce. AAD binds schema version, Client security UUID, credential UUID,
auth method and SSH credential generation; tampering, record swapping or wrong key
fails closed. Verify nonce uniqueness strategy and algorithm/library support before B.

Root keyring is a separately provisioned read-only secret file, outside `/app/data`,
public source, Compose values, environment dumps and SQLite backup. Key contents
never traverse browser/API. Restrict host0600 and broker UID access; keep a separate
controlled offline recovery copy. Never derive it from login passwords, fixed
Client passwords, `LOW_SECURITY_PASSWD` or session `SECRET_KEY`. No automatic weak
fallback or key regeneration. Feature off permits no Console key; feature enabled
requires validated key configuration at startup. Runtime key/broker failure fences
Console; coordination service can remain available. Invalid flag/policy values
fail startup rather than accidentally enabling access.

Admin Web writes use password/private-key replacement only; no reveal/export even
for Super Admin. Response projections expose configured state/method/versions, not
ciphertext, key, password or BMC username. Send bounded JSON text to avoid multipart
upload spooling private keys to disk. Proposed accepted OpenSSH key formats and
passphrase handling need library review: encrypt key+passphrase together if needed,
no ssh-agent/askpass/private temporary file. Remote authorized-key installation is
an operator's out-of-band action; gateway never runs ssh-copy-id or edits Client.

Candidate plaintext exists briefly in browser form, web parser, broker and SSH
library memory. Clear references/forms after each attempt; Python/JS immutable
strings/GC cannot guarantee forensic zeroization. Disable dumps/body/frame logging;
never claim encrypted SQLite prevents a compromised web process observing a new
credential. Authentication-only validation uses pinned host key before credential
transmission; no PTY/shell/remote command for Q70–Q72. Failure keeps old credential,
record and links. Audit only actor, Client ID/method/generation/result, never secret
or raw exception/banner. Notes warn administrators not to paste secrets.

Rotation plans (test before production):

1. **SSH credential replacement:** verify candidate host/auth outside DB lock;
   preview impact; commit new encrypted generation+audit+revocations; close every
   affected UART Web link without retry. Do not change remote tmux/minicom or
   automatically fall back to previous credential.
2. **Encryption KEK rotation:** provision new key ID separately, broker supports
   read-old/write-new, rewrap DEKs with fresh nonces in small version-CAS batches;
   checkpoint safely across interruption and verify every retained active secret.
   Audit key IDs/progress only. Crypto revision changes do not change the SSH
   identity or invalidate links merely for rewrap (engineering A4). Compromise
   incident is different: revoke all Console links/flows, replace remote credentials
   out of band, and review stolen backups; rewrapping cannot undo disclosure.
3. Retire old key from runtime only after all relevant envelopes are migrated.
   Retain old keys in controlled offline backup for retained historical SQLite
   backups. Never destroy a key while it is still needed for recovery.
4. Rehearse restore with old/new/missing/wrong keys and interrupted rotation using
   synthetic secrets; verify decryption through an auth mock, never reveal output.

## Direct BMC credentials

RD submits username/password only after target host trust. They live in one bounded
connect/auth attempt in RAM, never SQLite, audit, URLs, browser storage or retries.
Password is purged after failure/success; active SSH session does not require a
retained password. Re-authentication on reconnect asks again. At most3 submitted
auth attempts/flow, no automatic credential brute-force and no cross-flow failure
lockout; existing web-login rate limiter remains untouched. No remote username in
audit: Q3 applies to both supplied fields. Generic failure reasons must not echo
server authentication messages. A BMC may independently lock its remote account.

## SSH Host Key trust protocol

Use explicit SHA256 public-key fingerprints, algorithm and exact wire key, bound
to Client or SUT BMC identity plus numeric IP/port/revision. Do not use accept-any,
known_hosts='none', DNS lookup, automatic TOFU, fingerprint-only optimistic matching
or silently add a negotiated alternate key algorithm. Strong supported algorithm
baseline is proposed; legacy BMC compatibility/weak-algorithm exceptions require
separate review rather than silent downgrade (A9).

On explicit Connect/admin validation, retrieve handshake key **before userauth**.
Unknown or changed key yields a short-lived candidate challenge, old/new fingerprint
and OOB comparison instruction; close that candidate socket while user verifies.
Trust write requires fresh CSRF, bound challenge and optimistic version; initial
Client trust is approved by creating Admin (Q73), subsequent Client/BMC replacement
may be active RD (Q6/Q7). Changed Client key warning includes all affected SUT/RD/
session counts. Key update commits audit+trust+epoch+revocation, then closes all
Client UART links (Q74) or that SUT BMC links (Q75). Other transport and external
sessions remain untouched; no automatic reconnect.

Next actual handshake checks exact accepted key again before sending credentials;
never treat yesterday's preflight as proof of today's host. Stale challenge/new
endpoint/mismatched candidate fails, re-prompt with no secret transmission. A mere
observed key mismatch rejects that attempted connection; it does not silently
replace the trust pin or commit a failed admin edit. Existing pinned links are
revoked on successful trust change, or separate explicit incident response.

## Target validation and egress

No per-Lab CIDR inventory/allowlist is introduced (Q5). Validate syntax on Save,
network safety both on Save and immediately before every socket, and peer address
after connect. No hostname/DNS/rebinding path, proxy command, redirect or alternate
host fallback. Direct BMC22 only; admin Client port1..65535 only. SSH-agent, X11,
local/remote/dynamic TCP forwarding and arbitrary gateway exec all disabled.

Deny0.0.0.0/8,127/8,169.254/16 (including cloud metadata), multicast224/4,
reserved240/4, limited/directed broadcast, known non-unicast/special-purpose ranges,
all gateway/host/container interface addresses, routes to management/control-plane/
metadata services, and operator-maintained **sensitive destination deny entries**.
Use the current reviewed IANA special-purpose registry and actual interface/routes;
do not pretend `.is_private` alone is sufficient. Discover directed broadcasts
from actual interfaces/routes; unknown network masks cannot be inferred merely
from an RD IP. Test decimal/octal/hex forms, mapped IPv6 and alternate encodings.

An exclusion list for self/metadata is not a Lab subnet allowlist. Apply host/broker
network policy too, excluding host services even when a Docker route/NAT aliases
them. A proxy web app cannot securely infer that every remaining IPv4 SSH server is
really a BMC. Without a Lab allowlist the residual pivot/scanning risk is explicit.
Requirements §5 says 'deny public' while Q5 says any valid BMC IPv4; **C2 must be
resolved before live network enablement**. Save can retain a syntactically valid
endpoint; disputed address classes have no connect permission until reviewed.
Do not quietly implement RFC1918-only or permit all public targets as 'confirmed'.

## tmux and remote privilege limits

UART executor may only perform exact existing-session lookup and attachment via a
reviewed constrained helper; no new-session, kill-session/server, minicom, login
shell, SSH exec passthrough or socket path chosen by RD. Quote fixed argv safely
for SSH's string exec boundary; exact tmux target (`=name`) avoids prefix matching.
Backend tmux name grammar excludes whitespace, dots/colons, shell metacharacters,
newlines and leading options; limits are engineering A2 pending compatibility review.

Constrained account has no port forwarding/agent/X11 and no ordinary SSH shell.
Existing tmux/minicom ownership/settings must not be modified by gateway. Merely
allowing tmux attach with a writable server socket is insufficient: prefix-command,
window/session switching, run-shell or remote pane shell escape can grant Client
host access or affect another SUT. No unsafe promise that client-side key filtering
is a boundary. C1 requires demonstrated remote confinement that preserves existing
sessions, native size behavior, legitimate ANSI keys and shared writes. If that
cannot be achieved without prohibited tmux changes, stop live rollout and obtain
owner/security resolution; don't silently create per-SUT processes/servers.

An authorized **direct BMC shell**, or a shell already running in a UART pane, can
execute commands with that remote account's privilege. The gateway does not provide
power/firmware buttons or automated commands and blocks its own forwarding API;
it cannot truthfully prevent every pivot/power command typed into an authorized
shell. Remote least privilege/network isolation and owner operational rules remain
necessary. This boundary is distinct from securing the Client attach adapter.

## Approved HTTP/WS intranet exception

Future settings: CONSOLE_ENABLED=false, CONSOLE_ACCESS_POLICY=claim_only,
CONSOLE_ALLOW_INSECURE_HTTP=false by default. Strict Booleans and enum values;
unknown policy/invalid Boolean fails startup. Enabling HTTP Console additionally
requires explicit true, operator risk acknowledgement recorded without secrets,
trusted LAN bind/firewall restrictions and visible plaintext-transport warning.
These are designs, not edits to Compose in this PR. Keep existing host5088→80 and
SQLite/non-root runtime; no corporate DNS/certificate is required for the approved
HTTP exception. Do not silently convert the feature to HTTPS-only.

HTTP/WS exposes application cookies, ticket and BMC/Client provisioning credentials
and terminal streams to passive observers and active JS replacement/session theft.
HttpOnly, CSRF, encryption-at-rest and downstream SSH do **not** fix that exposure.
No-secret-in-URL/log/storage is still mandatory but not transport confidentiality.
Owner/operator must accept residual risk; do not display 'secure because SSH'.

Future HTTPS/WSS path uses trusted TLS termination, COOKIE_SECURE=true and explicit
allowed Origin/scheme/host/port. Trust forwarded proto/host only from configured
proxy peers; no client-supplied X-Forwarded-* override. HTTPS pages cannot downgrade
to ws://. Test WSS through the proxy and direct opted-in WS separately. Preserve
same-origin CSP, no external script/CDN, no unsafe-eval, frame denial/no-store,
Referrer-Policy:no-referrer for Console pages; add explicit connect-src for the
approved same-origin WS/WSS endpoint rather than weakening default-src globally.

Clipboard APIs may be denied over LAN HTTP. Right-click attempts clipboard read
only after user action and falls back to Ctrl+V/paste event; never demand an
insecure-browser flag or read clipboard on load. Multiline CR/LF/control handling
is covered in [contracts](contracts.md). Client output cannot trigger OSC52 writes,
automatic clipboard reads or arbitrary hyperlinks/downloads. No browser storage
or server transcript; a tab's RAM buffer survives reconnect only, capped10k lines.
