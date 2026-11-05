# PR proposal — CONSOLE-001 Phase E deployment integration

Adds a reviewed image-only Console overlay on merged Phase D. Web stays10001 with
SQLite; Broker stays10002 with independent KEK/private authenticated IPC. A separate
namespace initializer installs default-drop egress then drops to10003/zero effective
capabilities. Web/Broker remain read-only-root/non-root/cap_drop ALL, port5088→80,
SQLite bind, migrations and background coordination services are retained.

Startup requires exact Origins, private bind, explicit HTTP/WS risk attestation,
network policy and authenticated retained-envelope checks. Adds offline custodian
verification/atomic KEK rewrap with exclusive backup, rollback on failure and no
secret output. setup refuses Console stacks so a Web-only upgrade cannot silently
omit Broker/custody. No schema, existing terminal/coordination permission or
release-workflow change; defaults remain OFF/claim_only/insecure HTTP false.

Verified locally:358 pytest; Ruff/format/shell/JS/actionlint; three legacy Chromium
suites;34 Console Chromium checkpoints with actual isolated SSH/tmux/BMC; source
Docker, image-only Compose and installer regressions. Seven new actual deployment
checkpoint groups prove fresh install, UID/cap/mount/IPC/5088:80, raw-socket egress,
old-main image upgrade/business fingerprints, empty-directory cold restore,
compatible old-image rollback, wrong-KEK rejection and independent backup recovery.
Full commands, failure corrections and four acceptance categories are in
[verification](phase-e-verification.md). Manual authorized operator checks are in
[runbook](operator-runbook.md) and [recovery](rollback-and-recovery.md).

Review the scoped NET_ADMIN initializer, complete operator sensitive-host inventory,
separate key custodian/offline maintenance exception and HTTP plaintext exposure.
No host firewall is edited by the namespace initializer. Web's ordinary base bridge
is not claimed to have a kernel egress sandbox. C3 real Client/socket/shared shell,
C4 operator LAN/HTTP acceptance and C5 independent fingerprint distribution remain
OPEN. TLS/WSS end-to-end/real hardware/production recovery and hosted CI are not
claimed. No production access/activation, release/tag/image promotion, merge or
next phase. This is a candidate for independent review, not production acceptance.
