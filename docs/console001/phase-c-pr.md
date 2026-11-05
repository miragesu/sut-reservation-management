# Phase C PR creation fallback

Implementation commit: `81b08c0065393f86218eb0db91d267740fd93c5e`.
Branch pushed successfully: `feature/console001-phase-c`; target `main`.

`gh pr create --repo miragesu/sut-reservation-management --base main --head feature/console001-phase-c`
failed with exit1 on2026-11-05:

```text
Post "https://api.github.com/graphql": Forbidden
```

No PR was created by this command. No permission bypass, merge or publication was
attempted. [Create/review the comparison](https://github.com/miragesu/sut-reservation-management/compare/main...feature/console001-phase-c?expand=1).
Hosted branch CI is not verified by local acceptance results.

Suggested title: **CONSOLE-001 Phase C: Private SSH Broker and WebSocket Gateway**

## Ready-to-use PR body

Phase B had no live Console transport. This adds the separately launched non-root SSH Broker and authenticated WebSocket backend, with Console still OFF by default and existing coordination behavior preserved.

The Broker owns the encryption keyring and has no DB/public endpoint. Private IPC checks peer UID, HMAC, replay, boot incarnation and leases. Gateway resolves trusted records, validates pinned host keys before authentication, commits encrypted Client candidates only after real auth, and keeps BMC credentials per flow in RAM. Exact existing tmux attachment supports native Detach-to-shell and concurrent writers under the approved C1 amendment; C2 remains RFC1918 BMC/fixed22 without a Lab allowlist.

Tickets, fresh policy/epoch checks, two-layer read-only, ten logical slots, bounded IO/paste, finite retry/no replay, cancellation-safe quota cleanup and acknowledged generation fences cover the session lifecycle. Includes executable mock harness and CI integration; no Phase D terminal UI or production deployment/publication.

Validation:

- 337 pytest PASS, including 33 new Gateway/IPC cases; one preexisting Starlette/httpx deprecation warning.
- Ruff and formatting PASS; three existing Chromium suites PASS.
- Actual disposable OpenSSH/tmux/BMC, separate UID10001/10002 and DB/KEK mounts, full HTTP/WS→Broker→SSH, host pins, encrypted private keys, detach/concurrency/timeout/fencing/restart PASS.
- Source Docker build, final image-only Compose and installer fresh/rerun/backup-upgrade PASS;5088→80, non-root/capabilities/no-new-privileges, migration/persistence/cold recovery preserved.
- Owner ledger unchanged; no production connections, secrets/data changes, registry publication or merge.

Review [implementation](docs/console001/phase-c-implementation.md) and [verification](docs/console001/phase-c-verification.md). Actual Client account/default-socket topology, shared Linux account privileges, HTTP plaintext opt-in/OOB fingerprints (C3/C4/C5), key recovery/rotation/load and real-device acceptance remain production gates. Phase D requires separate authorization after review.
