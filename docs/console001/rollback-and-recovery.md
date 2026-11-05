# Console backup, rotation and recovery

Future authorized operator procedure; no production action is performed by this
PR. [Runbook](operator-runbook.md), [actual isolated evidence](phase-e-verification.md).
Never point these rehearsals at a company DB. Practice with synthetic fixtures
first and retain the precise compatible image/schema/key-ID manifest.

## Separate custody and cold backup

1. Disable new Console use for the approved maintenance window. Stop Web first
   (graceful Console fencing/closure), then Broker. Verify no live Console sessions;
   never kill remote tmux/minicom. Existing shared shell user processes/external
   clients are outside Gateway termination guarantees. Coordination writes stop.
2. Record reviewed Web/Broker digest, source commit, policy revision, Compose
   checksums, Alembic head (`console001_b01` for this change), key IDs, UID/mode and
   record counts. Keep private .env/SECRET_KEY and exact image lock securely.
   Do not print .env or key contents or use `compose config` without --quiet in logs.
3. Cold-archive the **whole** SQLite bind directory with numeric owners/modes after
   stopping all writers. Do not copy only sut.db while a writer/WAL may be active;
   do not overlay an old DB onto newer WAL/SHM. Place backups outside the live bind,
   mode0600, encrypted/offline under the database custodian. Verify archive integrity
   and schema/counts/FKs in a separate empty rehearsal directory.
4. A different key custodian retains matching versioned KEKs independently from
   SQLite and its backup tar. Preserve original key IDs needed by any retained
   credential/history/backup. Keep IPC capability protected separately; deliberate
   replacement requires Web+Broker restart. No key in image, .env, source, terminal
   transcripts or DB archive. Losing matching KEKs requires re-entering remote
   credentials through validated replacement; no recover/reveal endpoint exists.
5. Boot must require the intended /data mount **before Docker auto-restarts** any
   service. Backups and empty recovery directories need reviewed ownership/modes;
   never auto-create or chown an existing production data directory.

## Paired upgrade

The existing setup installer refuses Console deployments so it cannot update Web
alone. Fetch reviewed matching YAMLs and target immutable image, inspect release/
schema compatibility, pull all service references, approve maintenance and take the
cold backups above. Keep the existing project, data bind, SECRET_KEY and independent
custody. Use one `CONSOLE_IMAGE` for Web/Broker/namespace; no automatic alias updates.

Recreate namespace→Broker→Web with the reviewed files. Never `down -v`, delete a
bind, automatically migrate an old Named Volume or run destructive Alembic downgrade.
Preflight must verify IPC, key separation and **all retained envelopes** before Web
runs migrations or listens. Check health, schema head, integrity_check,
foreign_key_check, account IDs/password hashes, Labs/SUTs, current usages, history,
queue and reservation rows, and existing deadline semantics. Legitimate deadlines
may progress while services are online; compare intentional transitions separately.

If startup/migration/validation fails, retain candidate DB, logs containing only safe
metadata, and backups. No automatic schema rollback. Prefer disabling Console while
preserving coordination under a **compatible** image and investigating. New trust/
credential revisions and key IDs must be recorded before restoring any older set.

## Identity-preserving KEK rotation (not SSH credential replacement)

Custodian maintenance may temporarily access both DB and KEK, unlike the separated
runtime Broker. Run a reviewed network-none one-shot only with Web/Broker stopped;
never add both mounts to a runtime service. Provision a new independent32-byte KEK
under a new ID in a staged0600 keyring, retaining all needed old IDs and selecting
new active ID. Generate securely inside a trusted offline tool; do not pass keys
as command arguments, echo them or derive from SECRET_KEY. Back up old and staged
keyring independently before changing anything.

The image includes this offline CLI. Mount an existing stopped DB directory at
/app/data and the staged keyring read-only at /run/custody/keyring. Use the trusted
custodian identity with filesystem access (an explicitly authorized root one-shot
may be needed; Web/Broker themselves remain non-root). No Docker socket/network:

```sh
# Conceptual command after explicitly adding the two reviewed bind mounts:
# docker run --rm --network none --user 0:0 <mounts> --entrypoint python "$IMAGE" \
#   -m app.console_keyring rewrap --database /app/data/sut.db \
#   --keyring /run/custody/keyring --backup /app/data/pre-rewrap.db
```

`rewrap` refuses an existing backup path or active logical sessions, requires the
matching schema and verifies each retained encrypted credential. A single immediate
transaction updates only wrapped DEK/key ID/wrap nonce/crypto revision; ciphertext,
SSH generation/mapping/trust and coordination records remain. It audits only new
key ID/count. Interruption rolls back the transaction; the exclusive pre-change
backup remains. Repeat with a new backup path after verifying the prior state;
already-active-ID envelopes are verified without another rewrap. Never treat the
maintenance tool's short SQL lock as permission to leave Web/Broker running.

Use `verify` with the staged/matching keyring before startup:

```sh
# Same offline mounts/identity/no-network discipline:
# python -m app.console_keyring verify --database /app/data/sut.db \
#   --keyring /run/custody/keyring
```

No output contains plaintext credentials. A syntax-only `console_deployment
check-keyring` is not DB compatibility proof. Missing/wrong/AAD-tampered envelopes
fail. Safely install staged keyring as10002:10002/0600 outside DB, preserve independent
old copies, restore DB ownership/WAL hygiene if required, restart the paired stack
and run authenticated preflight. Retire runtime old keys only after **every retained
envelope** is rewrapped; do not destroy offline keys needed by old backups.
For credential/KEK compromise, close all Console links and replace remote SSH
credentials out of band; a rewrap alone cannot reverse disclosure.

## Compatible rollback and empty-directory restore

- For feature rollback, stop Web/Broker, keep encrypted data/keys, set Console false
  and use a schema-compatible coordination image. Do not enable an old image against
  a schema it cannot read. No migration is added by Phase E, but future releases
  may change that fact.
- For image/schema rollback, select the exact **pre-upgrade** cold DB/config and
  matching pre-upgrade image/keyring IDs. Restore into a newly created, empty,
  separately mounted rehearsal directory first; preserve UID10001/mode0700 and
  private Broker key permissions. Never overwrite the failing live directory.
- Verify archive digest, schema head, all retained account/usage/history/queue/
  reservation data, login/hash continuity, integrity/FKs and correct independent
  keyring. Authenticate through a disposable mock only during rehearsal.
- Start the old compatible image on that backup, not the migrated candidate DB;
  document any rollback data loss since the snapshot. Changing old image alone
  is not a database rollback. Old images may not contain the new overlay helpers;
  coordination-only rollback uses its matching base Compose with Console disabled.
- After independent acceptance and explicit operator approval, plan the production
  cutover separately. Restore/reboot/Client acceptance on the company host has not
  been executed here.

## Recovery and incident checklist

Missing/unmounted data: stop; do not initialize/bootstrap another database.
Wrong/missing key: stop Console; retrieve independently controlled matching backup,
never regenerate automatically. Pending revocations after crash: recover Broker
and Web incarnation/leases/outbox before a new Connect, never mark them delivered
manually. Lost IPC capability: deliberate fresh random capability + paired restart,
not session SECRET_KEY reuse. Unexpected Host Key: independent verification per
[runbook](operator-runbook.md); never accept-any or auto-TOFU.

C3 actual account/socket/shell permissions, C4 HTTP exposure and C5 OOB trust remain
open, regardless of successful synthetic backups. Independent owner/operator
review, real LAN validation and a separately authorized release are required.
