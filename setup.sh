#!/usr/bin/env bash
# Download this file from a reviewed commit, inspect it, then run: bash setup.sh
# Never use curl | bash. No source builds, volume migration or image publishing.
set -Eeuo pipefail
umask 077
REPOSITORY=mirage315/sut-reservation-management
PROJECT_NAME=sut-reservation
COMPOSE_REF=bdf7ae4274893a3b5e2b4a7d0ee9135e06223c3c
COMPOSE_SHA256=0e0dcac605fa8c275f6fcc7abe104b52ff5ed09b95a03f7e80236cf4f42d0d13
FALLBACK_VERSION=1.0.0
DATA_ROOT=/data
DATA_DIR=/data/sut-reservation-data
INSTALL_DIR=$PWD/sut-deployment
ALLOW_NEW_DATA=false
MIN_FREE_KIB=1048576
REQUESTED_VERSION=
UPGRADE=false

fail() { printf 'ERROR: %s\n' "$*" >&2; return 1; }
confirm() {
    local answer
    read -r -p "$1 [y/N]: " answer
    [[ "$answer" == y || "$answer" == Y || "$answer" == yes ]]
}
as_root() { if (( EUID == 0 )); then "$@"; else sudo -- "$@"; fi; }
compose() {
    # Shell exports must not silently override the persistent private configuration.
    env -u SECRET_KEY -u SUT_VERSION -u APP_BIND -u APP_PORT -u COOKIE_SECURE \
        -u LOW_SECURITY_PASSWD -u COMPOSE_PROJECT_NAME -u DATABASE_URL \
        docker compose --env-file "$INSTALL_DIR/.env" -p "$PROJECT_NAME" \
        -f "$INSTALL_DIR/compose.deploy.yaml" -f "$INSTALL_DIR/image.lock.yaml" "$@"
}
valid_version() {
    [[ "$1" == stable || "$1" == latest || "$1" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
}
preflight() {
    [[ "$(uname -s)" == Linux && "$(uname -m)" == x86_64 ]] || fail 'Requires Linux x86-64 (linux/amd64).'
    local tool
    for tool in docker curl sha256sum findmnt df ss ip od awk stat mktemp flock grep cut cmp tr; do
        command -v "$tool" >/dev/null || fail "Install required command: $tool"
    done
    docker info >/dev/null 2>&1 || fail 'Docker Engine is unavailable or this user lacks daemon access.'
    [[ "$(docker info --format '{{.OSType}}/{{.Architecture}}')" =~ ^linux/(x86_64|amd64)$ ]] || fail 'Docker daemon must be Linux amd64.'
    [[ "$(docker compose version --short)" =~ ^v?2\. ]] || fail 'Docker Compose v2 is required.'
    [[ -d "$DATA_ROOT" && ! -L "$DATA_ROOT" ]] || fail '/data is missing or a symlink.'
    [[ "$(findmnt -rn -M "$DATA_ROOT" -o TARGET)" == "$DATA_ROOT" ]] || fail '/data must be the intended mounted persistent filesystem; stop and fix the mount.'
    findmnt -M "$DATA_ROOT"
    df -h "$DATA_ROOT"
    local available
    available=$(df -Pk "$DATA_ROOT" | awk 'END {print $4}')
    [[ "$available" =~ ^[0-9]+$ ]] && (( available >= MIN_FREE_KIB )) || fail 'At least 1 GiB free on /data is required (plus database/backup capacity).'
    confirm 'Confirm this is the intended persistent filesystem and Docker boot ordering requires its mount' || fail 'Mount not confirmed.'
    if [[ ! -f "$INSTALL_DIR/.env" ]]; then
        [[ -z "$(ss -H -ltn 'sport = :5088')" ]] || fail 'Host TCP 5088 is occupied; resolve before fresh installation.'
    fi
}
load_config() {
    local key value line
    [[ -f "$INSTALL_DIR/.env" && ! -L "$INSTALL_DIR/.env" ]] || fail 'Private .env must be a regular file.'
    [[ "$(stat -c %a "$INSTALL_DIR/.env")" == 600 && "$(stat -c %u "$INSTALL_DIR/.env")" == "$EUID" ]] || fail '.env must be owned by this operator with mode 0600.'
    SECRET_KEY= APP_BIND= APP_PORT=5088 SUT_VERSION=stable LOW_SECURITY_PASSWD=false COOKIE_SECURE=false
    declare -A seen=()
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" == \#* ]] && continue
        [[ "$line" == *=* ]] || fail 'Unsupported .env syntax; never source .env as shell code.'
        key=${line%%=*}; value=${line#*=}
        [[ "$key" =~ ^[A-Z_]+$ ]] || fail "Invalid configuration key."
        [[ ! -v "seen[$key]" ]] || fail 'Duplicate .env keys are unsupported.'
        seen[$key]=1
        case "$key" in
            SECRET_KEY) SECRET_KEY=$value ;;
            APP_BIND) APP_BIND=$value ;;
            APP_PORT) APP_PORT=$value ;;
            SUT_VERSION) SUT_VERSION=$value ;;
            LOW_SECURITY_PASSWD) LOW_SECURITY_PASSWD=$value ;;
            COOKIE_SECURE) COOKIE_SECURE=$value ;;
            COMPOSE_PROJECT_NAME) [[ "$value" == sut-reservation ]] || fail 'Existing project differs; use the manual migration guide.' ;;
            SUT_IMAGE) fail 'Older SUT_IMAGE configuration detected. Preserve it and follow the manual adoption/migration guide.' ;;
            *) fail 'Unsupported .env key. Review configuration manually; no values were printed.' ;;
        esac
    done < "$INSTALL_DIR/.env"
    [[ "$SECRET_KEY" =~ ^[A-Za-z0-9_-]{32,}$ && "$SECRET_KEY" != *REPLACE* ]] || fail 'SECRET_KEY must be persistent, random and at least 32 characters (plain URL-safe value).'
    valid_version "$SUT_VERSION" || fail 'Invalid configured version.'
    [[ "$APP_PORT" == 5088 && "$COOKIE_SECURE" == false ]] || fail 'Installer supports trusted LAN HTTP on port 5088; preserve custom HTTPS deployments manually.'
    [[ "$LOW_SECURITY_PASSWD" == true || "$LOW_SECURITY_PASSWD" == false ]] || fail 'LOW_SECURITY_PASSWD must be true or false.'
    [[ "$APP_BIND" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail 'APP_BIND must be a host IPv4 address.'
    ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$APP_BIND" || fail 'Configured APP_BIND is not assigned to this server.'
}
probe_tag() {
    local error_file
    error_file=$(mktemp)
    if docker manifest inspect "$REPOSITORY:$1" >/dev/null 2>"$error_file"; then
        rm -f "$error_file"; return 0
    fi
    if grep -Eqi 'manifest unknown|no such manifest|manifest_unknown' "$error_file"; then
        rm -f "$error_file"; return 10
    fi
    rm -f "$error_file"
    fail 'Docker Hub lookup failed (network/TLS/auth/rate limit); no fallback attempted.'
}
select_version() {
    valid_version "$SELECTED_VERSION" || fail 'Choose stable, latest or an explicit MAJOR.MINOR.PATCH version.'
    local status
    if probe_tag "$SELECTED_VERSION"; then return; else status=$?; fi
    (( status == 10 )) || return "$status"
    [[ "$SELECTED_VERSION" == stable || "$SELECTED_VERSION" == latest ]] || fail 'Explicit version is unavailable; no substitution.'
    probe_tag "$FALLBACK_VERSION" || fail 'Verified fallback is unavailable; no installation performed.'
    printf 'Requested %s is absent. Available verified fallback: %s.\n' "$SELECTED_VERSION" "$FALLBACK_VERSION"
    confirm "Install $FALLBACK_VERSION instead" || fail 'Fallback declined.'
    SELECTED_VERSION=$FALLBACK_VERSION
}
prepare_data() {
    if [[ -e "$DATA_DIR" || -L "$DATA_DIR" ]]; then
        [[ -d "$DATA_DIR" && ! -L "$DATA_DIR" ]] || fail 'Existing data path is not a regular directory.'
        [[ "$(stat -c '%u:%g:%a' "$DATA_DIR")" == 10001:10001:700 ]] || fail 'Existing directory ownership/mode differs. No changes made; review manually.'
        if [[ ! -f "$INSTALL_DIR/.env" ]]; then
            fail 'Existing data directory without matching private configuration; use manual adoption/recovery. No changes made.'
        fi
        printf 'Preserving existing data directory and ownership.\n'
    else
        [[ "$ALLOW_NEW_DATA" == true ]] || fail 'Existing configuration has no data directory; refusing to silently create an empty database.'
        confirm "Create new $DATA_DIR (10001:10001, mode 0700)" || fail 'Directory creation declined.'
        as_root mkdir -m 700 "$DATA_DIR"
        as_root chown 10001:10001 "$DATA_DIR"
    fi
}
download_compose() {
    local temp expected_url
    expected_url="https://raw.githubusercontent.com/miragesu/sut-reservation-management/$COMPOSE_REF/compose.deploy.yaml"
    temp=$(mktemp "$INSTALL_DIR/.compose-download.XXXXXX")
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location "$expected_url" -o "$temp" || { rm -f "$temp"; fail 'Pinned Compose download failed.'; return 1; }
    if ! printf '%s  %s\n' "$COMPOSE_SHA256" "$temp" | sha256sum --check --status; then
        rm -f "$temp"; fail 'Compose checksum mismatch; existing Compose retained.'; return 1
    fi
    if [[ -f "$INSTALL_DIR/compose.deploy.yaml" ]] && ! cmp -s "$temp" "$INSTALL_DIR/compose.deploy.yaml"; then
        confirm 'Replace local Compose with this reviewed matching revision (existing config is backed up)' || { rm -f "$temp"; fail 'Compose replacement declined.'; return 1; }
        cp -p "$INSTALL_DIR/compose.deploy.yaml" "$INSTALL_DIR/compose.previous.yaml"
    fi
    mv "$temp" "$INSTALL_DIR/compose.deploy.yaml"
}
initialize_config() {
    local secret tmp
    printf 'Select a trusted local IPv4 address (not public Internet).\n'
    ip -4 -o addr show
    read -r -p 'APP_BIND IPv4 address: ' APP_BIND
    LOW_SECURITY_PASSWD=false
    if confirm 'Enable LOW SECURITY password mode (default No)'; then
        printf 'WARNING: 1-character passwords substantially increase unauthorized-access risk. Restricted internal networks only.\n'
        confirm 'I knowingly accept this risk' || fail 'Low-security mode not confirmed.'
        [[ "$IMAGE_VERSION" != 1.0.0 ]] || fail 'Published 1.0.0 does not support low-security mode. Wait for the reviewed new release.'
        docker run --rm --network none --entrypoint python "$TARGET_IMAGE" -c 'from app.core.config import Settings; assert "low_security_passwd" in Settings.model_fields, "Image does not support low-security mode"'
        LOW_SECURITY_PASSWD=true
    fi
    confirm "Use trusted LAN HTTP on $APP_BIND:5088 (COOKIE_SECURE=false)" || fail 'HTTP exposure not confirmed.'
    secret=$(od -An -N48 -tx1 /dev/urandom | tr -d ' \n')
    [[ ${#secret} == 96 ]] || fail 'Secure random generation failed.'
    tmp=$(mktemp "$INSTALL_DIR/.env-new.XXXXXX")
    printf 'COMPOSE_PROJECT_NAME=sut-reservation\nSUT_VERSION=%s\nAPP_BIND=%s\nAPP_PORT=5088\nCOOKIE_SECURE=false\nLOW_SECURITY_PASSWD=%s\nSECRET_KEY=%s\n' \
        "$SELECTED_VERSION" "$APP_BIND" "$LOW_SECURITY_PASSWD" "$secret" > "$tmp"
    chmod 600 "$tmp"
    # Hard link is atomic and refuses to overwrite any existing .env.
    ln "$tmp" "$INSTALL_DIR/.env" || { rm -f "$tmp"; fail '.env already exists; retained unchanged.'; return 1; }
    rm -f "$tmp"
    unset secret
}
resolve_image() {
    docker pull "$REPOSITORY:$SELECTED_VERSION" >/dev/null || fail 'Image pull failed.'
    local reference
    reference=$(docker image inspect "$REPOSITORY:$SELECTED_VERSION" --format '{{range .RepoDigests}}{{println .}}{{end}}' | grep -E "^$REPOSITORY@sha256:[0-9a-f]{64}$" | head -1)
    [[ "$reference" =~ @sha256:[a-f0-9]{64}$ ]] || fail 'No immutable digest returned by registry.'
    TARGET_IMAGE=$reference
    IMAGE_VERSION=$(docker image inspect "$TARGET_IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.version"}}')
    valid_version "$IMAGE_VERSION" && [[ "$IMAGE_VERSION" != stable && "$IMAGE_VERSION" != latest ]] || fail 'Image lacks an official version label.'
    if [[ "$SELECTED_VERSION" != stable && "$SELECTED_VERSION" != latest ]]; then
        [[ "$IMAGE_VERSION" == "$SELECTED_VERSION" ]] || fail 'Image version label does not match the selected version.'
    fi
    printf 'Will install version %s (selected %s), immutable reference %s\n' "$IMAGE_VERSION" "$SELECTED_VERSION" "$TARGET_IMAGE"
    confirm 'Proceed with this exact image' || fail 'Image selection declined.'
}
snapshot_records() {
    compose run --rm --no-deps -T --entrypoint python sut-management -c 'import json,sqlite3; d=sqlite3.connect("file:/app/data/sut.db?mode=ro",uri=True); print(json.dumps({t:[r[0] for r in d.execute("select id from "+t+" order by id")] for t in ("users","labs","suts","reservations","usage_histories")}))'
}
backup_existing() {
    local backup
    as_root install -d -m 700 "$DATA_ROOT/sut-backups"
    backup="$DATA_ROOT/sut-backups/pre-upgrade-$(date -u +%Y%m%dT%H%M%SZ)-$$.tar"
    compose stop sut-management
    snapshot_records < /dev/null > "$INSTALL_DIR/.records-before.json"
    as_root tar --numeric-owner --acls --xattrs -C "$DATA_DIR" -cpf "$backup" .
    as_root chmod 600 "$backup"
    as_root tar -tf "$backup" >/dev/null
    cp -p "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.previous"
    cp -p "$INSTALL_DIR/image.lock.yaml" "$INSTALL_DIR/image.previous.yaml"
    printf 'Cold backup: %s. Keep matching private config and previous image for schema-compatible recovery.\n' "$backup"
}
write_lock() {
    local tmp
    tmp=$(mktemp "$INSTALL_DIR/.image-lock.XXXXXX")
    printf 'services:\n  sut-management:\n    image: "%s"\n' "$TARGET_IMAGE" > "$tmp"
    mv "$tmp" "$INSTALL_DIR/image.lock.yaml"
}
verify_deployment() {
    local id health i
    for ((i=0;i<90;i++)); do
        id=$(compose ps -q sut-management)
        health=$(docker inspect "$id" --format '{{.State.Health.Status}}' 2>/dev/null || true)
        [[ "$health" == healthy ]] && break
        sleep 2
    done
    [[ "$health" == healthy ]] || fail 'Health failed. Preserve backup/data; inspect Compose logs. No automatic schema rollback.'
    [[ "$(compose port sut-management 80)" == "$APP_BIND:5088" ]] || fail 'Unexpected port mapping.'
    [[ "$(docker inspect "$id" --format '{{range .Mounts}}{{if eq .Destination "/app/data"}}{{.Type}}:{{.Source}}{{end}}{{end}}')" == "bind:$DATA_DIR" ]] || fail 'Unexpected SQLite mount.'
    compose exec -T sut-management alembic current
    compose exec -T sut-management alembic check
    compose exec -T sut-management python -c 'import sqlite3; d=sqlite3.connect("/app/data/sut.db"); assert d.execute("pragma integrity_check").fetchall()==[("ok",)]; assert not d.execute("pragma foreign_key_check").fetchall(); print("Database integrity: OK")'
    if [[ "$LOW_SECURITY_PASSWD" == true ]]; then
        compose exec -T sut-management python -c 'from app.core.config import Settings; assert getattr(Settings(),"low_security_passwd",False) is True, "Image does not support LOW_SECURITY_PASSWD"'
    fi
}
bootstrap_if_needed() {
    local count
    count=$(compose exec -T sut-management python -c 'import sqlite3; d=sqlite3.connect("/app/data/sut.db"); print(d.execute("select count(*) from users where role = ?",("super_admin",)).fetchone()[0])')
    [[ "$count" =~ ^[0-9]+$ ]] || fail 'Cannot determine bootstrap status.'
    if (( count == 0 )); then
        compose exec sut-management python -m app.scripts.bootstrap_admin
    else
        printf 'Super Admin already exists; bootstrap and credentials preserved.\n'
    fi
}
main() {
    if (( $# )); then
        [[ $# == 2 && "$1" == --upgrade ]] || fail 'Usage: bash setup.sh [--upgrade VERSION]'
        UPGRADE=true; REQUESTED_VERSION=$2
    fi
    [[ ! -L "$INSTALL_DIR" ]] || fail 'Install directory cannot be a symlink.'
    if [[ ! -d "$INSTALL_DIR" ]]; then mkdir -m 700 "$INSTALL_DIR"; fi
    [[ "$(stat -c %u "$INSTALL_DIR")" == "$EUID" && "$(stat -c %a "$INSTALL_DIR")" == 700 ]] || fail 'Deployment directory must be operator-owned with mode 0700.' 
    exec 9>"$INSTALL_DIR/.setup.lock"
    flock -n 9 || fail 'Another installer is running in this directory.'
    preflight
    local existing=false
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        existing=true; load_config
        [[ -f "$INSTALL_DIR/image.lock.yaml" && ! -L "$INSTALL_DIR/image.lock.yaml" ]] || fail 'Existing installation lacks its image lock. Follow manual adoption; no image change.'
        printf 'Existing configuration, secret and data will be preserved.\n'
        if [[ "$UPGRADE" == false ]]; then
            confirm 'Reconcile this installation using its recorded image (no version change)' || fail 'Rerun declined.'
            prepare_data
            download_compose
            compose config --quiet
            compose up -d --no-build --pull never
            verify_deployment; bootstrap_if_needed
            printf 'Installed URL: http://%s:5088/; storage %s; image ' "$APP_BIND" "$DATA_DIR"
            compose images
            return
        fi
        SELECTED_VERSION=$REQUESTED_VERSION
        printf 'Current recorded image:\n'; compose images
        printf 'Requested upgrade: %s\n' "$SELECTED_VERSION"
    else
        [[ "$UPGRADE" == false ]] || fail 'No existing installation to upgrade.'
        read -r -p 'Version [stable]: ' SELECTED_VERSION
        SELECTED_VERSION=${SELECTED_VERSION:-stable}
    fi
    select_version
    resolve_image
    if [[ "$existing" == false ]]; then
        [[ ! -e "$DATA_DIR" && ! -L "$DATA_DIR" ]] || fail 'Existing data without configuration; manual recovery required.'
        initialize_config; load_config; ALLOW_NEW_DATA=true
    fi
    if [[ "$LOW_SECURITY_PASSWD" == true ]]; then
        docker run --rm --network none --entrypoint python "$TARGET_IMAGE" -c 'from app.core.config import Settings; assert "low_security_passwd" in Settings.model_fields, "Target image does not support low-security mode"'
    fi
    prepare_data
    if [[ "$existing" == true ]]; then
        confirm 'Stop writes, make cold backup and replace the image (schema rollback is not automatic)' || fail 'Upgrade declined.'
        backup_existing
    fi
    download_compose
    write_lock
    if [[ "$existing" == true ]]; then
        local tmp
        tmp=$(mktemp "$INSTALL_DIR/.env-update.XXXXXX")
        awk -v version="$SELECTED_VERSION" 'BEGIN {found=0} /^SUT_VERSION=/ {print "SUT_VERSION="version; found=1; next} {print} END {if (!found) print "SUT_VERSION="version}' "$INSTALL_DIR/.env" > "$tmp"
        chmod 600 "$tmp"; mv "$tmp" "$INSTALL_DIR/.env"
    fi
    compose config --quiet
    compose up -d --no-build --pull never
    verify_deployment
    if [[ "$existing" == true ]]; then
        compose exec -T sut-management python -c 'import json,sqlite3,sys; before=json.load(sys.stdin); d=sqlite3.connect("file:/app/data/sut.db?mode=ro",uri=True); assert all(set(ids).issubset({r[0] for r in d.execute("select id from "+t)}) for t,ids in before.items()), "Pre-upgrade records are missing"; print("Users, Labs, SUTs, Reservations and Usage History preserved")' < "$INSTALL_DIR/.records-before.json"
    fi
    bootstrap_if_needed
    printf '%s %s %s\n' "$(date -u +%FT%TZ)" "$IMAGE_VERSION" "$TARGET_IMAGE" >> "$INSTALL_DIR/deployment.log"
    printf 'Installation verified: http://%s:5088/\nVersion: %s\nStorage: %s/sut.db\n' "$APP_BIND" "$IMAGE_VERSION" "$DATA_DIR"
    docker version --format 'Docker Engine {{.Server.Version}}'
    printf 'Sign in and change the temporary password, then sign in again. Permit TCP 5088 only from authorized internal clients.\n'
}
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    trap 'printf "Setup failed. Existing data and backups retained; inspect logs locally. Never automatically downgrade a migrated database.\n" >&2' ERR
    main "$@"
fi
