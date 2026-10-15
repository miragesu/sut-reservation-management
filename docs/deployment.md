# Administrator deployment guide — DEP-008

The primary production path uses the public, verified Linux amd64 image and
`compose.deploy.yaml`. No Python installation, Git clone, source checkout or image
build is needed on the server. GitHub Remote Build in the README is an optional
**developer/alternative path** that still uses a Named Volume.

## Administrator Quick Start — Linux Server

Required: Linux x86-64, Docker Engine, Docker Compose v2 supporting
`bind.create_host_path: false`, Internet access to Docker Hub for the initial pull,
a trusted internal network, a persistent `/data` filesystem, one reviewed
`compose.deploy.yaml`, and secure local configuration. Run Docker commands from an
authorized operator account. Docker access effectively grants host administration.

The verified v1.0.0 source is `5ebb4f62c30812d67c0383c0a426bdd0ea862796`.
[Release workflow succeeded](https://github.com/miragesu/sut-reservation-management/actions/runs/38746750990),
including anonymous digest pull/deployment. DEP-008 changes the deployment file;
**the old v1.0.0 tag's Compose still uses a Named Volume**. Obtain the newly reviewed
DEP-008 Compose revision separately from the unchanged image.

### A — Verify disk space and mount point

```bash
docker version
docker compose version
df -h /data
findmnt /data
```

**Stop if `/data` is not the intended mounted persistent filesystem**, is full or
is read-only. Have the server administrator fix the mount first. Configure host
boot/service ordering so Docker cannot start this application before `/data` is
mounted. `create_host_path: false` prevents a missing directory from being silently
created, but cannot detect an unmounted filesystem when a stale directory exists.

### B — Create persistent database directory

For a **new installation only**, after checking `/data`:

```bash
sudo mkdir -p /data/sut-reservation-data
sudo chown 10001:10001 /data/sut-reservation-data
sudo chmod 700 /data/sut-reservation-data
```

The container runs as UID/GID **10001:10001**. Linux checks these numeric IDs, so
this ownership allows SQLite to create its database, journal and lock files while
mode 700 excludes other host users. Do not use chmod 777 or run the app as root.
Existing deployments must follow the migration section before switching storage.

### C — Download deployment Compose

Create an administrator-owned directory outside any public checkout:

```bash
mkdir -p "$HOME/sut-deployment"
cd "$HOME/sut-deployment"
chmod 700 .
# Replace this with the FULL reviewed DEP-008 merge/source commit SHA.
DEPLOY_REF=REPLACE_WITH_REVIEWED_DEP008_COMMIT_SHA
curl --fail --location "https://raw.githubusercontent.com/miragesu/sut-reservation-management/$DEPLOY_REF/compose.deploy.yaml" -o compose.deploy.yaml
```

The replacement is intentional: do not use an unreviewed moving branch or the
historical v1.0.0 Compose. Record the chosen revision. You need only this YAML and
private settings, not the entire repository.

### D — Configure environment

The address below is an example for the intended server. Replace it with your
server's actual trusted LAN interface. Run this **once in a new install directory**;
it refuses to overwrite an existing `.env`. It uses the existing image's Python
inside a one-off container to generate a random secret without installing Python:

```bash
IMAGE='mirage315/sut-reservation-management@sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6'
docker pull "$IMAGE"
( set -eu; umask 077; set -C
  {
    printf '%s\n' 'COMPOSE_PROJECT_NAME=sut-reservation'
    printf 'SUT_IMAGE=%s\n' "$IMAGE"
    printf '%s\n' 'APP_BIND=10.88.26.99' 'APP_PORT=5088' 'COOKIE_SECURE=false'
    printf 'SECRET_KEY='
    docker run --rm --network none --entrypoint python "$IMAGE" -c 'import secrets; print(secrets.token_urlsafe(48))'
  } > .env
)
chmod 600 .env
```

Check that the command succeeded before continuing; if interrupted, remove only
the incomplete new `.env` and repeat. Keep the secret persistent across restarts
and upgrades. Do not print `.env`, paste it into tickets, commit it to public
GitHub, or store publisher Docker Hub credentials on this server. Keep an
encrypted recovery copy separately. `COOKIE_SECURE=false` is required for trusted
LAN HTTP; use true with correctly configured HTTPS. Do not expose this service to
the public Internet. Prefer HTTPS for sensitive internal traffic.

### E — Start application

Run all subsequent Compose commands from this directory:

```bash
docker compose -f compose.deploy.yaml config --quiet
docker compose -f compose.deploy.yaml pull
docker compose -f compose.deploy.yaml up -d --no-build
docker compose -f compose.deploy.yaml ps
docker compose -f compose.deploy.yaml logs --tail=100 sut-management
curl --fail http://10.88.26.99:5088/health
```

Use `config --quiet`: full rendered config includes the secret. Wait for healthy
status. Startup runs Alembic migrations before Uvicorn listens on `0.0.0.0:80`.
Host **5088 → container 80** is preserved, with a single worker and enabled
background deadline processor. UID/GID 10001, all capabilities dropped,
no-new-privileges, private bridge network and container-local unprivileged-port
threshold 80 remain mandatory. Do not change the host sysctl or use host networking.

### F — Initialize Super Admin (one time)

```bash
docker compose -f compose.deploy.yaml exec sut-management \
  python -m app.scripts.bootstrap_admin
```

Answer the interactive prompts: **Username** (login identifier), **Display name**,
**Team**, **Work email** (unique), and **Temporary password**, entered twice without
echo (12–128 characters). Choose organization-approved values; no default password
exists. Bootstrap works only before a Super Admin exists. Do not rerun it to reset
an existing administrator. First login forces a password change; that change
signs out all sessions, so log in again with the new password.

### G — Open application

Open **http://10.88.26.99:5088/** from an authorized internal browser. The server
firewall must permit TCP 5088 from approved internal clients; ask the network
administrator for the organization's specific rule rather than opening it publicly.
In-app notifications work over LAN HTTP. Browser desktop notifications usually
require HTTPS, explicit permission and an open page; Inbox is the fallback.

### H — Verify database persistence

```bash
sudo stat -c '%u:%g %a %n' /data/sut-reservation-data
sudo ls -ln /data/sut-reservation-data/sut.db*
docker inspect "$(docker compose -f compose.deploy.yaml ps -q sut-management)" \
  --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}} {{.Source}} -> {{.Destination}}{{end}}{{end}}'
```

Expect directory `10001:10001 700`, database
`/data/sut-reservation-data/sut.db`, and `bind /data/sut-reservation-data -> /app/data`.
WAL/SHM files may appear or disappear normally. Do not directly edit SQLite files.
After creating initial records, use `docker compose -f compose.deploy.yaml restart`
and verify records remain. Permanent deletion of this directory **loses production
data**; neither images nor GitHub contain a recovery copy.

## First-Time Administrator Operations

1. Sign in as Super Admin, replace the initial password, then sign in again.
2. Open Administration → Labs (`/labs`) and create the two Taiwan Labs using your
   approved names. Do not run the development seed on production.
3. Open SUT inventory (`/suts`) and register approximately 20 SUTs. Select Lab and
   enter Name, Platform, Owner Team, BMC IP and Host IP. Names are manually assigned
   and unique within a Lab, including archived names. Keep real inventories private.
4. Open Administration → Users (`/admin/users`) to create RD accounts with unique
   usernames/work emails and securely delivered temporary passwords. There is no
   self-registration. Assign User for normal coordination, Lab Admin for inventory
   and coordination administration across both Labs, and Super Admin only for
   trusted account/role/system administrators. Each new user must change password.
5. Dashboard Claim records reported use; estimates do not impose a usage cap.
   Release records actual Usage History. Queue is FIFO and notifies the next
   eligible user to manually Claim; an idle SUT without a queue is Claimed directly.
   Reservations are future bookings, at most 24 hours, starting within 30 days.
   Check in within 15 minutes of start (and before end); coordinate handoff if
   occupied. No automatic physical handoff or overdue release occurs.
6. Use History (`/history`) for retained usage records; Reservations/Calendar for
   bookings, My Usage for current use and Inbox for notifications.
7. SUT Detail → operational state allows Maintenance / Out of Service with a reason
   and acknowledgement of existing activity. New Claim/Queue/Reservation actions
   are blocked; existing use/history/bookings remain. Restore Normal after review.
8. Deactivate departing accounts through Users after reviewing the impact preview
   and acknowledging outstanding resources. Deactivation revokes access, retains
   history and may leave resources needing administrator attention. Never delete
   database rows manually. The last active Super Admin is protected.
9. Archive retired SUTs through inventory administration. Resolve active usage,
   queues and current/future reservations first; blockers prevent archival.
   Archived inventory/history is retained and administrators can restore it.

The system coordinates **reported** use. It never blocks SSH, BMC, network, power
or other hardware access. Coordinate real access and handoff with colleagues.

## SQLite Backup and Restore

### Cold backup

Store archives on `/data` or another large filesystem, with encrypted/off-host
copies and a retention schedule. They contain account hashes and internal records.
Stop all application writers (including any external tools) before copying files.
The service stop also stops its deadline processor.

```bash
sudo install -d -m 700 /data/sut-backups
stamp=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP="/data/sut-backups/sut-data-$stamp.tar"
docker compose -f compose.deploy.yaml stop sut-management
# Continue only when stop succeeds. Tar includes sut.db, WAL and SHM when present.
sudo tar --numeric-owner --acls --xattrs -C /data/sut-reservation-data -cpf "$BACKUP" .
sudo chmod 600 "$BACKUP"
sudo tar -tf "$BACKUP"
# Restart only after backup succeeded; investigate any tar error first.
docker compose -f compose.deploy.yaml start sut-management
```

Preserve a protected copy of Compose, `.env`, selected Compose revision and image
digest alongside the backup recovery records (never in Git). Copying only a live
`sut.db` is unsafe. Application indefinite history retention is not backup.

### Safe restore rehearsal — separate empty directory

Use a trusted archive and the matching image/schema. Never overwrite live database
files. The following commands use a new path and abort if it already exists:

```bash
RESTORE_DIR="/data/sut-restore-$(date -u +%Y%m%dT%H%M%SZ)"
# Set BACKUP to a chosen existing archive, not a wildcard.
BACKUP=/data/sut-backups/REPLACE_WITH_CHOSEN_ARCHIVE.tar
sudo mkdir -m 700 "$RESTORE_DIR"
sudo tar --numeric-owner --same-owner --acls --xattrs -C "$RESTORE_DIR" -xpf "$BACKUP"
sudo stat -c '%u:%g %a %n' "$RESTORE_DIR" "$RESTORE_DIR/sut.db"
# Read-only integrity check, mounted only into an offline helper; no app starts.
docker compose -f compose.deploy.yaml run --rm --no-deps -T \
  --volume "$RESTORE_DIR:/restore:ro" --entrypoint python sut-management -c \
  'import sqlite3; d=sqlite3.connect("file:/restore/sut.db?mode=ro",uri=True); assert d.execute("PRAGMA integrity_check").fetchall()==[("ok",)]; assert not d.execute("PRAGMA foreign_key_check").fetchall(); print("SQLite integrity and foreign keys: OK")'
```

Preserve all archived file ownership/modes, including UID/GID 10001. If a read-only
check needs WAL recovery and cannot open, use an isolated **writable copy** of the
restored directory for recovery/checking; do not alter the retained archive or live
production files. Before accepting recovery, test a separate copy with a separate
Compose project, bind path and loopback host port (e.g. 5089), the matching digest
and retained secret. Verify health, Alembic revision, login, users, SUTs,
Reservations, Usage History and notifications. Starting the app may migrate the
copy and process elapsed deadlines. Never run two writers against the same DB.
For actual recovery, stop production and use a reviewed Compose override pointing
to the verified restored directory; retain the old directory for recovery.

## Software Upgrade Procedure

1. Review new release notes/schema compatibility. Make and verify a cold backup.
2. Record the current image digest, Compose revision/project name and private config.
   Store configuration copies with mode 600 in a protected recovery directory.
   `docker compose -f compose.deploy.yaml images` shows the running image;
   `docker image inspect IMAGE_REF --format '{{json .RepoDigests}}'` shows digests.
3. Select a new **successfully verified** public image digest, never `latest`. Edit
   only `SUT_IMAGE` in private `.env`; retain `SECRET_KEY`, project and bind path.
4. Run `docker compose -f compose.deploy.yaml config --quiet`, then `pull`.
5. Run `docker compose -f compose.deploy.yaml up -d --no-build --force-recreate`.
   Never delete `/data/sut-reservation-data` or attach an empty path during upgrade.
6. Check `ps`, logs, `/health`, and
   `docker compose -f compose.deploy.yaml exec sut-management alembic current`.
   Confirm migration success and healthy port 5088 → 80.
7. Sign in and verify existing users, SUTs, Reservations, Usage History and background
   notifications remain correct. Rehearse each release on a restored copy first.

An old image may not support a newer schema. Startup `upgrade head` is not a schema
downgrade. Rollback may require a **matching pre-upgrade backup restored into a
separate empty directory** and the compatible prior image/Compose. Do not overlay
old WAL/database files, perform unreviewed downgrades, or assume image rollback is
sufficient. GitHub pushes do not redeploy a running server automatically.

## Existing Named Volume deployment — separate manual migration

Do not apply fresh-install instructions over an existing deployment. No automated
migration or volume deletion is provided. Schedule downtime and record its existing
Compose project, image, persistent secret and actual mount identity:

```bash
docker inspect EXISTING_CONTAINER_ID --format '{{index .Config.Labels "com.docker.compose.project"}}'
docker inspect EXISTING_CONTAINER_ID --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}} {{.Name}} {{.Source}}{{end}}{{end}}'
```

1. Retain the old Compose and `.env`. Verify `/data`, stop the **old** service using
   its original Compose/project, and confirm no writer remains.
2. Set `OLD_VOLUME` to the inspected exact volume name and `IMAGE` to the current
   verified digest. Export a cold archive without changing the volume:

   ```bash
   sudo install -d -m 700 -o "$(id -u)" -g "$(id -g)" /data/sut-migration-backups
   # Bash: noclobber prevents overwriting a previous migration archive.
   ( set -C; umask 077
     docker run --rm --user 0 --network none --entrypoint tar \
       --mount "type=volume,src=$OLD_VOLUME,dst=/old,readonly" \
       "$IMAGE" -C /old -cpf - . > /data/sut-migration-backups/sut-migration.tar
   )
   ```

   Require successful commands; verify the archive exists and is complete. Do not restart the old writer while making the copy.
3. Use `sudo mkdir -m 700 /data/sut-reservation-data` **without `-p`** so an existing
   destination fails rather than being overlaid. Extract the trusted archive there, preserving ownership and modes:

   ```bash
   sudo tar --numeric-owner --same-owner -C /data/sut-reservation-data \
     -xpf /data/sut-migration-backups/sut-migration.tar
   ```
4. Rehearse integrity and recovery as above. Switch to the reviewed DEP-008 Compose,
   keeping the existing project name and secret. Start and inspect the actual bind
   mount, health and retained application records.
5. Keep the old Named Volume untouched and the old deployment stopped. Do not run
   `docker volume rm`, `down -v`, or prune commands. If migration fails before new
   writes, stop the new app and use the retained compatible original deployment.
   After new writes, rollback requires reconciliation to avoid data loss.

## Troubleshooting

Use `docker compose -f compose.deploy.yaml ps -a` and
`docker compose -f compose.deploy.yaml logs --tail=100 sut-management`. Review logs
locally; redact internal inventory/contact details before sharing. Do not publish
`.env`, full rendered Compose, passwords or database files.

| Symptom | Action |
| --- | --- |
| Container not starting | Check logs, `config --quiet`, image architecture (linux/amd64), mount and secret; do not rebuild v1.0.0. |
| Missing/invalid SECRET_KEY | Ensure private `.env` is in the Compose directory and key is random, persistent, at least 32 characters, with no placeholder. A previously exported shell variable overrides `.env`; unset stale overrides. Preserve the original key to retain sessions. |
| SQLite permission denied | Check numeric directory/file ownership 10001:10001, mode 700 on directory, writable mounted filesystem and free space. Correct only the verified application data path; do not chmod 777. On SELinux hosts ask an administrator for a narrowly scoped container-compatible label; do not disable SELinux globally. |
| `/data` not mounted | Stop the app; correct the intended filesystem mount and verify `findmnt /data` before restart. Never create a replacement data directory on the root disk. |
| TCP 5088 occupied | Use `sudo ss -ltnp 'sport = :5088'` to identify the owner. Resolve with the server administrator; do not kill unknown services. Keep the documented production port unless a deliberate network change is approved. |
| Browser cannot connect | Verify healthy status, server interface exists (`ip address`), curl health on the configured address, bind mapping, TCP 5088 firewall and client routing. A cloud check cannot prove company LAN reachability. |
| Login session not persisting | Trusted LAN HTTP needs COOKIE_SECURE=false; HTTPS should use true. Preserve SECRET_KEY, check browser cookies/time and sign in again after password changes (all sessions rotate). Never weaken authentication. |
| Migration failed | Keep stopped, preserve data/backup, read exact Alembic error, check permissions/disk and release compatibility. Do not delete DB, stamp revisions or downgrade blindly. Restore a compatible backup if necessary. |
| Docker Hub pull failed | Check exact digest/repository, outbound DNS/TLS/proxy/network and rate limits. Public pull needs no publisher token. Do not disable TLS, substitute latest, rebuild the image or put Docker Hub publishing secrets on the server. |

## Release ownership and alternative developer checks

Publishing is separate from administrator installation. Existing
`.github/workflows/release.yml` publishes only reviewed new `v*` tags merged into
main, validates versions/tests/build/Compose, then authenticates with GitHub Actions
secrets `DOCKERHUB_USERNAME` and scoped `DOCKERHUB_TOKEN`. It publishes OCI
revision/version labels, provenance and SBOM, followed by anonymous digest pull and
full deployment verification. Never move existing release tags or overwrite
v1.0.0. No publishing credentials belong on production servers.

From a development/test checkout, with dependencies, Docker and Chromium:

```bash
SUT_SMOKE_IMAGE=mirage315/sut-reservation-management@sha256:56b9e9ad2e5fb60b852fe214a7d79679875f526045e2d722d589fc472791cae6 SUT_SMOKE_PULL=1 python scripts/container_smoke.py
```

The runner substitutes a unique temporary host bind directory, never the real
`/data/sut-reservation-data`; no image build occurs in image mode. It verifies
non-root/port/security settings, migrations, login/browser flows, persistence,
background deadlines and isolated cold recovery. The recovery helper still uses a
separate disposable Named Volume. Historical source-build smoke remains available
for developers only. See implementation status for actual results; company Linux
host, LAN/firewall, persistent mount boot ordering and real recovery remain external
acceptance gates.
