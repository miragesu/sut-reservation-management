# DEP-007 verification — Issue #6

Base: latest main `3b59e2e` (merged Day 3/DEP-006). Branch: `feat/dep007-dockerhub-release`. Issue: https://github.com/miragesu/sut-reservation-management/issues/6.

## Acceptance mapping

| Requirement | Implementation / observed evidence |
| --- | --- |
| Version-tag publishing, successful tests before push | `release.yml` accepts explicit `v*` pushes, validates Docker-compatible SemVer and requires ancestry on main. Its reusable checks run pytest/browsers/source build/image-only deployment; the publisher also tests its loaded candidate before registry login/push. Invalid/unsafe version-ref cases are automated in `test_release_version.py`. Actual release trigger/push remains unexecuted. |
| Scoped secrets, pinned official actions, least privileges | Full official action SHAs resolved from their upstream refs; actionlint 1.7.7 passes. GitHub token contents:read only; registry secrets are publisher-step-scoped and never passed to reusable checks/build args. No literal registry token exists in source. |
| Version, digest, provenance and no latest | Metadata action emits only the validated full version (`latest=false`); source/revision/version OCI labels, BuildKit provenance/SBOM and successful digest deployment are summarized. Post-push test uses an empty credential directory to require public anonymous pull. Implementation inspected/linted; no real digest is claimed yet. |
| Production Compose image only | `compose.deploy.yaml`, no build field, requires SUT_IMAGE/SECRET_KEY, loopback default, linux/amd64, explicit UID 10001, cap_drop ALL, no-new-privileges, namespaced threshold 80, named data volume and deadline processor. Real rendered-model tests fail without image/secret and succeed without SUT_GIT_REF. |
| Existing runtime/data behavior | Full 122-case suite passes (103 retained + 19 version-gate cases); baseline, Day 2 and Day 3 browser runners pass. No application models/services/schema/entrypoint changes. |
| Operator deployment without source/build | Loaded local candidate is deployed from a fresh directory containing only compose.deploy.yaml; config asserts no build/source/.git/Dockerfile, up uses --no-build. A second run succeeds with a failing Git executable placed first on PATH, proving image mode does not invoke Git. |
| Port/privileges/migrations/login/persistence/recovery | Both source-build and image-only runs assert actual 5088→80, EXPOSE/healthcheck80, UID10001, CapEff/Prm/Bnd=0, NoNewPrivs=1, container namespace threshold80 and port79 denied. They exercise startup migration rejection, login/password gate, Chromium UI, existing data/session retention across recreation, background catch-up/live deadlines/deduplication and cold restore into another empty volume. |
| First-time/upgrade/rollback documentation | `docs/deployment.md`: one Compose plus secure export/optional private .env, pull/up/bootstrap, project/volume identity when switching files, provenance, backup/empty-volume restore and schema-compatible rollback. No untested cross-version rollback or production-host restore is claimed. |
| Preserve Remote Build | Existing compose.yaml/local override remain; the generic runner retains remote-ref mode. Published branch Remote Build **PASS** at `c6c3065158f088ff3c8224ef2177b7f6d7882e0a` with the full port/privilege/browser/background/persistence/backup-restore runner. |
| Actual publication/separate server/LAN | **NOT VERIFIED**. No version tag or registry write was created in this task. Secret values are absent in the cloud environment; GitHub secret-name query is Forbidden and Docker Hub metadata HTTP tunneling is Forbidden. Repository secret setup/public visibility and a real accepted tag release with anonymous pull must be verified externally. |

## Commands observed locally

- Ruff check and format; compileall: PASS.
- Official actionlint **1.7.7**: PASS for both workflows. Binary archive SHA-256 verified against the official release checksum before use.
- `.venv/bin/pytest -q`: **122 passed**, 86.68s; one non-failing Starlette/httpx TestClient deprecation warning.
- `scripts/browser_smoke.py`, `scripts/browser_day2.py`, `scripts/browser_day3.py`: PASS.
- Rendered image-only Compose: missing image and missing SECRET_KEY both fail closed; valid settings require no SUT_GIT_REF and contain no build configuration: PASS.

```bash
DOCKER_CONFIG=/tmp/sut-docker-config SUT_BUILD_NETWORK=host \
  SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
  SUT_SMOKE_EXPORT_IMAGE=mirage315/sut-reservation-management:dep007-validation \
  .venv/bin/python scripts/container_smoke.py
DOCKER_CONFIG=/tmp/sut-docker-config \
  SUT_SMOKE_IMAGE=mirage315/sut-reservation-management:dep007-validation \
  .venv/bin/python scripts/container_smoke.py
```

Both PASS, including browser/background/persistence/independent-volume restore. The local validation tag was **not pushed**. Image mode is rerun with Git deliberately unavailable and passes. The source builder uses the cloud's inherited proxy and approved CA as an ephemeral BuildKit secret; TLS and package hashes stay verified. Image-only mode does not need those build settings. Only random synthetic test volumes are deleted.

Optional pinned Remote Build also passes at the implementation SHA above. Hosted Application checks also **PASS** at that SHA: [run 38744064962](https://github.com/miragesu/sut-reservation-management/actions/runs/38744064962), conclusion SUCCESS, 5m 10s, including all pytest/browser/source/image-only checks. These do not establish a registry release; the version-tag release workflow itself remains untriggered until authorized secrets/version setup.

## External release gates

1. Owner verifies public Docker Hub repository and securely sets/verifies GitHub Secrets DOCKERHUB_USERNAME/DOCKERHUB_TOKEN.
2. Merge the reviewed workflow, choose an unused version and explicitly push its tag. Verify the entire release, including anonymous published-digest pull, succeeds.
3. Deploy the accepted digest from image-only Compose on the actual separate Linux server, retaining the existing project/volume/secret. Verify company LAN firewall/two clients and production backup/restore/rollback.

DEP-007 end-to-end publication/production acceptance is **NOT DONE** until these gates pass. No hardware control or production data/secrets are added.
