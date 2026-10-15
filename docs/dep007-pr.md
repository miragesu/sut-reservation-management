## Behavior

Adds DEP-007 version-tag releases to `mirage315/sut-reservation-management` and makes `compose.deploy.yaml` the image-only production operator path. Explicit validated `v*` tags on merged main commits run complete regression checks and a loaded-candidate Compose smoke before registry login/push. The SHA-pinned Docker actions publish only the full version plus immutable digest, provenance/SBOM, then require an anonymous digest pull/deployment check. Ordinary main pushes do not publish and no token is hardcoded.

The image-only deployment preserves 5088:80, UID10001, zero capabilities/no-new-privileges, private-network port binding, startup migrations, background deadlines and the named SQLite volume. Existing GitHub Remote Build remains optional. The administrator guide covers secure one-file-plus-secret setup, bootstrap, provenance, same-volume upgrades and schema-compatible backup/restore/rollback.

## Verification

- 122 pytest cases pass (103 retained, 19 release-ref cases); Ruff, format, compile and official checksum-verified actionlint pass.
- Baseline/Day 2/Day 3 Chromium flows pass.
- Source build and source-free image-only Compose pass actual port/privilege/health/login/browser, session/data recreation persistence, deadlines/restart deduplication and independent-volume cold restore. Image mode also passes with Git deliberately unavailable; missing image/secret fail closed.
- Hosted application CI / optional Remote Build results are recorded in implementation status before handoff.

## External acceptance

No release version/tag was created, no Docker Hub image was pushed, and no registry pull is claimed. The cloud has no publisher credential bindings; GitHub secret metadata and Docker Hub metadata requests are Forbidden. Repository secrets may exist remotely but cannot be verified here. Owner must securely configure/verify public Docker Hub repository and GitHub Secrets, merge, choose a version and run the real release/anonymous-pull gate. Separate production Linux/LAN/firewall/two-client and production recovery acceptance remain unverified.

See `docs/dep007-verification.md`, `docs/deployment.md`, `docs/implementation-status.md` and `TASKS.md`. DEP-007 end-to-end publication/production acceptance remains NOT DONE until external gates pass. No application behavior, schema or hardware-control integration changes.

Refs #6.
