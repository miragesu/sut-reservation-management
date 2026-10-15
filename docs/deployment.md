# Administrator installation and maintenance — DEP-009

Use the one-file installer on Linux x86-64 with Docker Engine, Docker Compose v2,
Docker daemon access, root or sudo rights for preparing storage/backups, curl and normal Linux utilities (`findmnt`, `ss`, `ip`, `flock`,
`sha256sum`). No Git clone, host Python, source build or manual digest entry is
required. Installation needs Internet access to public GitHub and Docker Hub, a
trusted internal network, and an intended persistent filesystem mounted at `/data`
with at least 1 GiB free **plus enough space for data and cold backups**. Configure
firewall access to TCP5088 for authorized internal clients only.

## Administrator Quick Start — Linux Server

Download `setup.sh` from a **reviewed full DEP-009 commit** (replace the placeholder
with the approved PR merge/source SHA; it is not a moving `main` URL):

```bash
SETUP_REF=REPLACE_WITH_REVIEWED_DEP009_FULL_COMMIT_SHA
curl --proto '=https' --tlsv1.2 --fail --location \
  "https://raw.githubusercontent.com/miragesu/sut-reservation-management/$SETUP_REF/setup.sh" -o setup.sh
less setup.sh
bash setup.sh
```

Never execute `curl | bash`. The reviewed script embeds the full source commit
and SHA256 of its matching Compose. It downloads that HTTPS file automatically
and rejects tampering; a newer script can intentionally pin a newer Compose.
Review/trust the script itself and its pinned checksum before execution.

The script creates a private `sut-deployment` directory **under the directory from
which it is invoked**. Always invoke later runs from the same parent directory
with the same operator account. It locks concurrent runs from that directory.
Changing directory/project or losing its configuration is not a reinstall method.
Do not run multiple installations against the same SQLite data directory.

### Interactive installation

1. Confirm the displayed `/data` mount and free space; installation stops if the
   exact persistent mount is missing. Never substitute a directory on the root disk.
2. Select `stable` (recommended), `latest`, or an explicit version such as `1.0.0`.
   Registry/network errors stop installation. If **only a preferred alias is absent**,
   the script offers the verified `1.0.0` fallback and requires confirmation. It
   never substitutes a different explicit version. It shows the actual image label
   version and immutable reference and asks before proceeding.
3. Select an IPv4 address assigned to the trusted LAN interface; e.g. `10.88.26.99`
   only if actually assigned to your server. Confirm trusted LAN HTTP on5088.
4. Answer No (default) to low-security passwords. Enabling requires a warning and
   a second explicit confirmation, plus an image supporting the feature.
5. Confirm creation of `/data/sut-reservation-data`, UID/GID 10001:10001, mode 0700.
   Existing data without its matching private configuration is refused. An existing
   directory with unexpected permissions is never chowned silently. The installer
   does not migrate Named Volumes.
6. A 96-character secret from `/dev/urandom` is generated locally without display
   and saved in mode0600 `.env`. Keep it and its encrypted recovery copy persistent.
   The `.env` contains project `sut-reservation`, selected `SUT_VERSION`, port5088,
   confirmed `APP_BIND`, `COOKIE_SECURE=false`, and `LOW_SECURITY_PASSWD=false` by
   default. Shell exports cannot override installer-managed values.
7. The script validates Compose, starts image-only with `--no-build`, and verifies
   health, actual5088→80 mapping, bind identity, Alembic revision/schema and SQLite
   integrity/foreign keys. It never builds source or publishes images.
8. For a database with no Super Admin, the existing secure interactive CLI asks for
   Username, Display Name, Team, Work Email and Temporary Password (twice without
   echo). There is no default password. An existing Super Admin skips bootstrap.
9. Open the displayed URL, sign in and **change the temporary password**, then sign
   in again. The script displays installed application and Docker Engine versions
   and persistent database path `/data/sut-reservation-data/sut.db`.

Installation files include the downloaded Compose, private `.env`, a local
`image.lock.yaml` override and `deployment.log`. The operator selects simple
versions; the lock records the exact resolved digest so reruns cannot silently
adopt a moved tag. Do not edit/delete the lock to upgrade. Restrict the directory
to0700 and keep configuration/record snapshots out of Git/tickets. Never use
`set -x`, print `.env`, or share full rendered Compose (it contains SECRET_KEY).
Only `config --quiet` is suitable for normal validation.

### Published versus planned versions

**Verified published:** `1.0.0`, source `5ebb4f62c30812d67c0383c0a426bdd0ea862796`,
[successful release](https://github.com/miragesu/sut-reservation-management/actions/runs/38746750990).
Its audit digest is
`sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6`.
It does **not** implement LOW_SECURITY_PASSWD. The installer refuses that feature
with 1.0.0, rather than pretending that a new environment variable changes old code.

**Planned, not published by DEP-009:** `1.0.1`, `latest` and `stable` aliases under
this new promotion policy. Registry lookups determine actual availability at run
time; this documentation never assumes an alias exists. No automatic upgrade occurs
when a registry alias moves. Version 1.0.1 is tentative until review, merge, an
explicit new release tag, and successful release validation.

## Boot ordering and mount safety

Arrange host boot so Docker's `unless-stopped` containers cannot start before the
intended `/data` mount. The installer requires the operator to confirm this setup;
it does not change system services. A host administrator can review a Docker systemd
drop-in (affects **all** Docker workloads) such as:

```ini
[Unit]
RequiresMountsFor=/data
[Service]
ExecStartPre=/usr/bin/mountpoint -q /data
```

Ensure `/data` has its correct persistent mount configured in `/etc/fstab`, verify
the local `mountpoint` executable path, reload systemd and schedule any Docker
restart with the host administrator. Test a reboot and failed mount before production
acceptance. `create_host_path:false` prevents missing directory creation, but cannot
recognize a stale directory under an unmounted filesystem by itself.

## LOW_SECURITY_PASSWD — consciously insecure option

Absent/false means minimum 12 characters (existing MINIMUM_PASSWORD_LENGTH can raise
it); no uppercase/lowercase/digit/special-character mix is required. True accepts
1–128 characters, still rejecting empty or entirely whitespace passwords. Only
Boolean true/false are valid; malformed values such as `yes`, `1` or `on` fail
configuration validation. Unicode counts as characters. The128-character maximum
remains in both modes.

This applies equally to bootstrap, all three roles, administrator-created accounts,
resets and password changes, in HTML and API. **Short passwords substantially
increase unauthorized-access risk**; enable only knowingly on a restricted internal
network. It does not change existing credentials or relax SECRET_KEY: that must
always contain at least32 random characters. Argon2id, login rate limits, sessions,
revocation, CSRF, RBAC and first-login mandatory password replacement remain enabled.

After a supporting release is installed, changing the toggle requires container
recreation, not an image rebuild. Stop/review with the operator, edit only the
Boolean in private `.env`, and rerun the installer using its retained lock. Do not
copy real credentials or the `.env` into public GitHub. HTTPS is preferred; the
installer's COOKIE_SECURE=false is strictly for confirmed trusted LAN HTTP. Custom
HTTPS/proxy configurations require the manual operator path, not this HTTP installer.

## First-Time Administrator Operations

After Super Admin login and password replacement:

1. Administration → Labs (`/labs`): create the two approved Taiwan Labs.
2. Inventory (`/suts`): register approximately20 SUTs with manually chosen unique
   per-Lab Name, Platform, Owner Team, BMC IP and Host IP. Keep inventories private.
   Do not run fictional development seeds on production.
3. Administration → Users (`/admin/users`): create RD accounts and securely deliver
   temporary passwords outside the app. Users change them at first login. Assign
   User for normal coordination, Lab Admin for inventory/coordination administration
   across both Labs, and Super Admin only for trusted account/role administrators.
4. Claim records reported use; Release records actual Usage History. FIFO Queue
   notifies eligible users to manually Claim. Idle/no-queue SUTs are Claimed directly.
   Reserve future intervals (≤24h, start within30days), check in before start+15min
   and booked end, and coordinate handoff if still occupied. Overdue use is never
   automatically released. History is retained indefinitely.
5. SUT Detail → Maintenance / Out of Service requires a reason/impact acknowledgement,
   blocks new coordination actions, and preserves existing use/bookings/history.
   Return to Normal after review.
6. Deactivate departing accounts only after reviewing outstanding resources; access
   is revoked but records remain. Resolve resources requiring administrator attention.
   Archive retired SUTs after resolving usage/queue/bookings; archive blockers apply,
   retained history remains and administrators can restore SUTs. The last active
   Super Admin cannot be disabled or demoted.

The application coordinates reported use; it does **not** block SSH, BMC, network,
power or hardware access. Inbox is authoritative for notifications; private-LAN HTTP
usually cannot show desktop notifications without HTTPS and explicit permission.

## Maintenance commands

From the retained install directory, define this helper for the current shell:

```bash
cd sut-deployment # from the same parent where setup was first run
# Include the retained digest lock on EVERY manual management command.
dc() { docker compose --env-file .env -p sut-reservation -f compose.deploy.yaml -f image.lock.yaml "$@"; }
dc config --quiet
dc ps -a
dc logs --tail=100 sut-management
sudo stat -c '%u:%g %a %n' /data/sut-reservation-data
sudo ls -ln /data/sut-reservation-data/sut.db*
```

Do not run plain Compose without `image.lock.yaml`: that would follow the selected
mutable alias instead of the installed digest. A normal installer rerun preserves
`.env`, SECRET_KEY, image lock, data and existing administrator; it does not resolve
or pull a new alias. Never use `down -v`, volume pruning or direct SQLite edits as
routine maintenance. Deleting the persistent directory loses production data.

## SQLite Backup and Restore

Keep archives on `/data` or another large filesystem, protected/encrypted and
copied off-host. Schedule regular backups and rehearsals independently of history
retention. Stop **all** writers before file-level backup, including the service's
background processor. Retain matching image lock, Compose and private configuration.

```bash
sudo install -d -m700 /data/sut-backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="/data/sut-backups/sut-data-$stamp.tar"
dc stop sut-management
# Proceed only after successful stop. Whole directory includes WAL/SHM when present.
sudo tar --numeric-owner --acls --xattrs -C /data/sut-reservation-data -cpf "$BACKUP" .
sudo chmod 600 "$BACKUP"
sudo tar -tf "$BACKUP"
# Investigate any backup error before restarting writers.
dc start sut-management
```

Rehearse in a separate, newly created empty directory; never overwrite live files:

```bash
BACKUP=/data/sut-backups/REPLACE_WITH_CHOSEN_ARCHIVE.tar
RESTORE_DIR="/data/sut-restore-$(date -u +%Y%m%dT%H%M%SZ)"
sudo mkdir -m700 "$RESTORE_DIR" # no -p: fail if destination exists
sudo tar --numeric-owner --same-owner --acls --xattrs -C "$RESTORE_DIR" -xpf "$BACKUP"
sudo stat -c '%u:%g %a %n' "$RESTORE_DIR" "$RESTORE_DIR/sut.db"
dc run --rm --no-deps -T --volume "$RESTORE_DIR:/restore:ro" --entrypoint python sut-management -c \
  'import sqlite3; d=sqlite3.connect("file:/restore/sut.db?mode=ro",uri=True); assert d.execute("pragma integrity_check").fetchall()==[("ok",)]; assert not d.execute("pragma foreign_key_check").fetchall(); print("Integrity and foreign keys: OK")'
```

Preserve numeric10001:10001 ownership and0700 directory permissions. If WAL recovery
needs writes, use a disposable **writable copy**, never the production path or
retained archive. Test another copy with the matching image/schema, a separate
Compose project, explicit restored bind path and loopback5089, retaining the secret.
Verify Alembic, health, login, users, SUTs, Reservations, History and notifications;
startup may process expired deadlines or migrate the test copy. Never attach two
application writers to one database. For real recovery stop production, point a
reviewed override to the verified restored directory, and retain the old data.

## Administrator-initiated upgrade and rollback

From the **same parent directory** as the original run:

```bash
# Download/review a new setup.sh from an approved fixed source if needed first.
bash setup.sh --upgrade 1.0.1 # only AFTER that release is actually published/verified
# Or explicitly request the currently approved stable alias:
# bash setup.sh --upgrade stable
```

The installer shows current image and requested target, resolves/shows actual version
and digest, and requests confirmation. Pulling alone never replaces a container.
Before replacement it stops writes, snapshots retained record identities and makes
a cold archive under `/data/sut-backups`, saving private `.env.previous` and
`image.previous.yaml`. It retains SECRET_KEY, bind path and credentials, updates the
selected version/lock, then recreates without building. Health, migrations, integrity
and retained User/Lab/SUT/Reservation/History IDs must verify; existing Super Admin
is not bootstrapped again. Check representative records and workflows in a browser
before accepting an upgrade. Review disk space for the full backup, not just1GiB.

Failure leaves data and backups intact and reports the error; it never performs an
automatic schema downgrade. A prior image may not read a newly migrated database.
Rollback requires either verified schema compatibility or a matching pre-upgrade
backup restored into a separate empty directory, matching old image/configuration,
and manual verification. Do not overlay old DB/WAL files or assume changing image
alone is safe. Do not rerun blindly after an interrupted initial setup: preserve
files and investigate missing config/data/lock instead of creating a new database.

## Older installation / Named Volume migration

DEP-008 `.env` files using SUT_IMAGE require deliberate adoption; the installer
refuses to reinterpret them. Back up the old deployment and retain its secret,
Compose, project name, image and mount identity. For bind deployments, confirm the
same path/ownership, create a private version-based `.env` preserving the exact
secret/HTTP settings, and create `image.lock.yaml` pinned to the **existing** image.
Use the exact service-only override format generated by setup; do not upgrade while
adopting. Only use the installer if project is `sut-reservation` and its supported
HTTP configuration matches. Preserve custom configurations with manual management.

Named Volumes are **never automatically migrated or deleted**. Schedule downtime:

```bash
docker inspect EXISTING_CONTAINER_ID --format '{{index .Config.Labels "com.docker.compose.project"}}'
docker inspect EXISTING_CONTAINER_ID --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}} {{.Name}} {{.Source}}{{end}}{{end}}'
```

Stop the old service using its original Compose/project and ensure no writer remains.
Record the exact volume name in OLD_VOLUME and the verified current image in IMAGE.
Export to a private operator-owned backup directory on `/data` (never use a guessed
volume name), then restore into a new empty bind directory:

```bash
sudo install -d -m700 -o "$(id -u)" -g "$(id -g)" /data/sut-migration-backups
( set -C; umask 077
  docker run --rm --network none --user 0 --entrypoint tar \
    --mount "type=volume,src=$OLD_VOLUME,dst=/old,readonly" \
    "$IMAGE" -C /old -cpf - . > /data/sut-migration-backups/sut-migration.tar
)
sudo mkdir -m700 /data/sut-reservation-data # refuse existing destination
sudo tar --numeric-owner --same-owner -C /data/sut-reservation-data \
  -xpf /data/sut-migration-backups/sut-migration.tar
```

Require successful commands, validate archive/integrity/ownership and rehearse
recovery. Deliberately adopt the new Compose using the retained project/secret and
same existing digest before any upgrade. Verify actual bind and retained records.
Leave the old Named Volume untouched and old service stopped; no volume removal or
pruning. After new writes, rollback requires reconciliation to avoid lost changes.

## Release owner: official versions, latest and stable

No image is published by installation or this PR. After review/merge, prepare a new
unused annotated Git tag (tentativelyv1.0.1). `.github/workflows/release.yml` accepts
reviewed `v*` tags from main, runs all tests/build/Compose/security assertions, tests
a candidate, then rejects an already-existing explicit registry tag before push.
Registry lookup failures fail closed. Release concurrency is serialized. Restrict
Docker Hub write permission and GitHub tag creation; registry-side immutability for
explicit version tags is recommended to defend against external concurrent writers.
Never move Git tags or overwrite explicit Docker versions, including 1.0.0.

Only **after** the explicit image passes anonymous digest pull/deployment does the
job promote that same official (non-prerelease) digest to `latest`. If publication
succeeds but later validation fails, aliases remain unchanged; the explicit version
is unaccepted and must not be overwritten. No multi-tag transaction exists in Docker
Hub; promotion is intentionally delayed and each alias write is checked afterward.
OCI source/revision/version, provenance/SBOM and digest summary remain available.

`stable` requires a separate explicit **workflow_dispatch** on main naming an
existing official version. Before enabling it, the repository owner must create
GitHub Environment **dockerhub-stable**, configure required trusted reviewers with
self-review prevented, and only then set repository variable
`STABLE_PROMOTION_ENABLED=true`. Restrict dispatch/environment access. The stable
job is disabled without that variable; successful development builds alone cannot
promote. An authorized operator dispatches, reviewers approve the environment job,
and it verifies source ancestry plus anonymous published-digest deployment **before**
registry login and stable update. GitHub Actions secrets DOCKERHUB_USERNAME and a
scoped DOCKERHUB_TOKEN belong to the publisher only. Production pulls are public.
Do not dispatch stable for 1.0.0 automatically; any future approval is a separate
explicit operation. Rerunning a release with an existing explicit tag fails safely.

## Troubleshooting

Use `dc ps -a`, `dc logs --tail=100 sut-management`, `dc config --quiet`. Redact
internal data before sharing logs. Never publish `.env`, DBs or record snapshots.

| Problem | Action |
| --- | --- |
| Preflight fails | Check Linux amd64, Docker daemon permission, Compose v2, required utilities, exact `/data` mount, disk space and5088 availability. Never bypass missing persistent storage. |
| Compose checksum failure | Stop. Verify reviewed setup revision and network origin; do not disable checksum/TLS. Old Compose is retained. |
| Missing registry tag | Only stable/latest may offer confirmed1.0.0 fallback. Explicit missing versions, network/auth/TLS/rate-limit errors stop; do not substitute latest silently. |
| SECRET_KEY invalid | Keep original persistent random 32+ character value in0600 `.env`. Never use low-security mode to weaken it. Installer-managed values override shell exports. |
| Low-security password rejected | Only the new supporting release accepts it;1.0.0 does not. Use explicit true/false, recreate container, check image/config. Do not rebuild/overwrite1.0.0. |
| Permission denied / SQLite read-only | Verify mount, free space, UID/GID 10001 and mode 0700. Existing unexpected ownership requires deliberate administrator review; do not chmod777 or run app as root. SELinux needs a narrowly scoped host policy/label; never disable it globally. |
| Existing data/config missing | Stop and recover matching config/secret/lock. No silent new DB, bootstrap reset, volume migration or recreation occurs. Retain backups. |
| Port occupied / browser unreachable | Identify listener with `sudo ss -ltnp 'sport = :5088'`, confirm local interface, health,5088→80 mapping, firewall and LAN routing. Do not kill unknown services or expose publicly. |
| Session does not persist | LAN HTTP requires COOKIE_SECURE=false; HTTPS uses true. Retain SECRET_KEY, check browser cookies/time. Password changes revoke sessions and require login again. |
| Migration/upgrade failed | Keep backup/data; inspect exact Alembic error and compatible image. Never delete DB, stamp revisions blindly, downgrade schema automatically or restart old image on incompatible DB. |
| Interrupted bootstrap | Rerun from same parent with retained lock/config. Existing Super Admin is detected; no credential reset. If none exists, the secure CLI prompts again. |

Actual server reboot/mount ordering, SELinux, production firewall/two LAN clients,
real administrator inventory workflow and bind-directory disaster recovery remain
external acceptance gates. Cloud tests never establish production LAN acceptance.
