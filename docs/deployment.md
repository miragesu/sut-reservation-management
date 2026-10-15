# DEP-007: administrator deployment from Docker Hub

The primary operator path is `compose.deploy.yaml` and a tested public image from **mirage315/sut-reservation-management**. The server needs Linux x86-64, Docker Engine/Compose v2, registry/network access and persistent storage; it does not need Git, Python, source code or build tooling. Linux amd64 is the only release platform currently tested. `compose.yaml` remains the optional pinned GitHub Remote Build path; `compose.local.yaml` remains for developers.

A release is not assumed to exist merely because this workflow is committed. All version numbers below are examples. Use a version/digest whose release workflow actually succeeded, including its anonymous public pull/deployment check.

## Release owner: one-time setup and publishing

1. Create or verify the **public** Docker Hub repository `mirage315/sut-reservation-management`.
2. In the GitHub repository's **Settings → Secrets and variables → Actions**, securely set `DOCKERHUB_USERNAME` to `mirage315` and `DOCKERHUB_TOKEN` to a scoped Docker Hub access token with read/write access to this repository. Use the narrowest available repository permissions; deletion access is unnecessary. Do not paste tokens into issues, chat, YAML or production-server `.env`. Server operators pulling this public image need no publisher token.
3. Merge/review the release workflow and application changes into `main`. Restrict who may create/change release tags. Choose an unused Docker-compatible SemVer tag, such as `v1.0.0` or `v1.0.0-rc.1`; no leading zero numeric components or `+build` metadata. Never move a published Git version tag or overwrite a released Docker tag. Docker tags can be mutable; the **digest** is the immutable production identity.
4. From a maintainer's checkout (not the production server), after deciding the actual release version:

```bash
git fetch origin main --tags
git switch main
git merge --ff-only origin/main
# Example only; choose an unused reviewed version, then explicitly publish its tag.
git tag -a v1.0.0 -m 'Release 1.0.0'
git push origin v1.0.0
```

Only explicit `v*` tag pushes trigger `.github/workflows/release.yml`; ordinary main/PR pushes do not publish. The workflow rejects invalid versions and commits not already merged into main, then runs the reusable complete application checks (pytest, browsers, source build and source-free image Compose). The publisher builds/loads a linux/amd64 candidate, exercises the full operator deployment runner **before login/push**, then publishes the version tag with OCI source/revision/version labels, BuildKit provenance and SBOM. It does not publish `latest`.

After pushing, a separate empty Docker credential directory is used for an **anonymous registry pull by immutable digest** and the same deployment checks. The successful run summary records version, full source commit and `mirage315/sut-reservation-management@sha256:...`. A push can succeed before a later smoke fails: if the overall run fails, treat the tag as unaccepted, investigate, and release a new version; do not silently move the existing version. Provenance/SBOM are build metadata, not a claim of cryptographic signing.

Actions are pinned to full official-repository commit SHAs; workflow token permissions are `contents: read`. No Docker Hub secrets are passed to the reusable test workflow. Protect the main branch and release tags to preserve this trust boundary.

## First-time server deployment

Choose a protected working directory and download **only** the reviewed Compose file. Replace the placeholder with the release tag or full reviewed source SHA corresponding to the image:

```bash
mkdir -p sut-deployment
cd sut-deployment
chmod 700 .
DEPLOY_REF=REPLACE_WITH_REVIEWED_TAG_OR_SHA
curl --fail --location "https://raw.githubusercontent.com/miragesu/sut-reservation-management/$DEPLOY_REF/compose.deploy.yaml" -o compose.deploy.yaml
export COMPOSE_PROJECT_NAME=sut-reservation
export SUT_IMAGE='mirage315/sut-reservation-management@sha256:REPLACE_WITH_SUCCESSFUL_RELEASE_DIGEST'
# Example tag alternative, only after that version is actually published/tested:
# export SUT_IMAGE=mirage315/sut-reservation-management:1.0.0
```

Record and reuse the **same project name**. It determines the default volume name, e.g. `sut-reservation_sut-data`. When migrating an existing Remote Build deployment, use its existing Compose project name and verify the actual `/app/data` named volume before switching files. Both files use the same `sut-management` service and `sut-data` volume key; inventing a new project name can attach an empty database instead of the existing one.

Supply a strong persistent `SECRET_KEY` (at least 32 random characters, preferably generated in a password manager). An image/public Compose cannot safely contain a shared secret. A single Compose file is enough on disk if configuration is securely exported for **each management shell**:

```bash
# Bash: secret is read without echo and is not included in command history.
read -r -s -p 'Persistent SECRET_KEY: ' SECRET_KEY
printf '\n'
export SECRET_KEY
export APP_PORT=5088
export APP_BIND=127.0.0.1
# For trusted private LAN HTTP only; use true with HTTPS.
export COOKIE_SECURE=false
```

Set `APP_BIND` to the server's actual trusted LAN interface for LAN access; loopback is the safe default. Restrict inbound host TCP 5088 to approved LAN clients. Alternatively keep settings in an administrator-owned local `.env` with mode 600, outside any public checkout/backups accessible to others. This extra private file is optional convenience, not something to commit. Preserve the same `SECRET_KEY` across updates; changing it invalidates signed sessions. Do not put Docker Hub publishing credentials on this public-image server.

```bash
docker compose -f compose.deploy.yaml config --quiet
docker compose -f compose.deploy.yaml pull
docker compose -f compose.deploy.yaml up -d --no-build
docker compose -f compose.deploy.yaml ps
docker compose -f compose.deploy.yaml logs --tail=100
curl --fail http://127.0.0.1:5088/health # use APP_BIND's address when bound to the LAN interface
# Interactive one-time bootstrap; no default administrator password exists.
docker compose -f compose.deploy.yaml exec sut-management python -m app.scripts.bootstrap_admin
```

Sign in and replace the temporary password before normal access. Confirm Dashboard, Claim/Release/Queue/Reservation and notifications from authorized browsers. No public sign-up or hardware access control is introduced.

The image runs Alembic before serving. Failed migrations prevent startup. SQLite stays in `sut-data:/app/data` at `/app/data/sut.db`, not in the image. Host **5088 → container 80**, Uvicorn `0.0.0.0:80`, UID/GID 10001, zero capabilities, no-new-privileges and the private-network sysctl `net.ipv4.ip_unprivileged_port_start=80` are retained. Do not switch to host networking. One Uvicorn worker and the independent deadline processor remain enabled.

In-app notices work with trusted HTTP; private-IP desktop notifications generally require HTTPS and explicit browser/OS permission. Alerts are not guaranteed after the site closes. Prefer a trusted HTTPS internal endpoint when desktop alerts are required.

## Verify image provenance

Use the successful release workflow's source commit, version, digest and deployment results. On the server:

```bash
docker image inspect "$SUT_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
docker image inspect "$SUT_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.version"}}'
docker image inspect "$SUT_IMAGE" --format '{{json .RepoDigests}}'
```

Compare revision/version with the reviewed release and pin the published digest. A downloaded Compose file is configuration, not proof that an image/version was successfully published. Do not use `latest` for production.

## Backup, upgrade and rollback

Before changing image/version or Compose, record the current image digest, source revision, Compose/project name, named volume and private settings. Retain the matching application/Compose revision for recovery. Stop writers and back up the **entire** directory, including WAL/SHM files:

```bash
umask 077
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M%S)
docker compose -f compose.deploy.yaml stop sut-management
docker compose -f compose.deploy.yaml run --rm --no-deps -T --entrypoint sh sut-management -c 'tar -C /app/data -cf - .' > "backups/sut-data-$stamp.tar"
docker compose -f compose.deploy.yaml start sut-management
```

Check command success and protect/encrypt/off-host the backup; it contains internal data and authentication records. Copying a live SQLite file alone is not a consistent backup. An application retention policy is not disaster recovery.

For upgrade, read migration/release notes, keep the matching reviewed Compose file, set `SUT_IMAGE` to the **new successful release digest**, then run `pull` and `up -d --no-build` again with the same project/volume/secret. Check health, logs, migration version, login, inventory/history and background processing. GitHub pushes do not update the server automatically. Normal `down` retains data; **never run `down -v` for routine operations**.

Rollback to an earlier digest is safe only if its code supports the current database schema. Startup `upgrade head` does not automatically undo newer migrations. Never run an unreviewed downgrade or overlay old SQLite/WAL files onto a live database. If schemas differ, restore a matching pre-upgrade backup into a **new empty volume**, retaining the current volume for recovery:

```bash
# App stopped; select the matching previous digest (example placeholder).
export SUT_IMAGE='mirage315/sut-reservation-management@sha256:REPLACE_WITH_PREVIOUS_DIGEST'
docker compose -f compose.deploy.yaml stop sut-management
docker pull "$SUT_IMAGE"
docker volume create sut-restored
# Recovery helper only: root preserves the archived UID/GID, application remains non-root.
docker run --rm -i --user 0 --entrypoint sh -v sut-restored:/app/data "$SUT_IMAGE" -c 'test -z "$(ls -A /app/data)" || { echo "Recovery volume is not empty" >&2; exit 1; }; exec tar -C /app/data -xf -' < backups/CHOSEN_BACKUP.tar
```

Use a unique, verified **empty** recovery volume name. In the same `compose.deploy.yaml`, replace only the bottom volume declaration to point to it:

```yaml
volumes:
  sut-data:
    external: true
    name: sut-restored
```

The service still mounts `sut-data:/app/data`. Start the matching image with `up -d --no-build`, retaining UID/GID 10001 ownership. Run `PRAGMA integrity_check`, `PRAGMA foreign_key_check`, verify Alembic revision and representative login/history/notices before accepting recovery. Preserve this explicit volume declaration when updating Compose in future. The automated disposable runner rehearses cold restore to another empty volume; it is not a production-host restore or proof of cross-version schema compatibility.

## Reproducible deployment validation

From a developer/test runner with dev dependencies, Docker and Chromium (never against production data):

```bash
# Builds/tests source once and retains a local test image; does not publish it.
SUT_SMOKE_EXPORT_IMAGE=mirage315/sut-reservation-management:validation python scripts/container_smoke.py
# Copies only compose.deploy.yaml into a fresh directory; up uses --no-build.
SUT_SMOKE_IMAGE=mirage315/sut-reservation-management:validation python scripts/container_smoke.py
# After a real public release exists, require an actual registry pull:
SUT_SMOKE_IMAGE=mirage315/sut-reservation-management@sha256:REPLACE_WITH_DIGEST SUT_SMOKE_PULL=1 python scripts/container_smoke.py
```

The runner validates image metadata/health, actual 5088:80, PID 1 UID/capabilities/no-new-privileges, port 79 denied, fresh/populated migrations, forced-password/login, Chromium UI, volume/session persistence, background deadline recovery/deduplication and cold restore. Only its random synthetic test projects/volumes are removed. Local image-only success **does not establish Docker Hub publication/pull**, a separate Linux host or company LAN acceptance. See `docs/dep007-verification.md` for observed results and external gates.
