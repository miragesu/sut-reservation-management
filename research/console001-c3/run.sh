#!/bin/sh
# Local disposable research only. Never publish this research fixture.
set -eu
cd "$(dirname "$0")"
local_docker() {
    env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
        docker --host=unix:///var/run/docker.sock "$@"
}
local_docker info --format '{{.ServerVersion}}'
# Preserve registry credentials. Put only writable buildx state under /tmp if needed.
export BUILDX_CONFIG="${BUILDX_CONFIG:-/tmp/console001-buildx}"
local_docker build --secret "id=ca,src=${CONSOLE001_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}" \
    -t console001-c3-research .
local_docker run --rm --network none --hostname console001-c3-mock \
    --tmpfs /run/mock:rw,nosuid,nodev,mode=0700 --pids-limit 128 --memory 256m --cpus 1 \
    --security-opt no-new-privileges:true console001-c3-research
