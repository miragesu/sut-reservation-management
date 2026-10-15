## Scope and behavior

Turn the planning-only repository into a working Day 1 FastAPI/Jinja2 application with local authentication and inventory management. Super Admins provision temporary accounts, users must replace their initial password before normal web/API access, and role/status/password changes take effect server-side. Either admin manages both labs; SUT deletion archives with conflict guards, and maintenance states preserve existing activity.

Adds complete SQLAlchemy domain models and initial Alembic migration `fd0b3a205c15`, SQLite serialized writes, safe profile/account management, resource impact/Needs attention, initial Card/Table Dashboard, and authenticated typed JSON APIs. Dashboard uses shared filters, natural Name/Status sorting and 30-second read-only polling. No hardware control or production data/secrets are introduced.

Production Compose uses a required reviewed GitHub ref, configurable port 5088, a durable named SQLite volume, non-root image and migration-before-startup. A local build override, secure CLI bootstrap, synthetic-only dev seed, CI workflow and deployment/backup guidance are included.

## Verification

- `ruff check backend scripts`, `ruff format --check backend scripts`, compileall and diff whitespace checks pass.
- `pytest -q`: **39 passed**. Covers migrations, auth/CSRF/role checks, mandatory password change, session revocation, profile allowlisting, inventory CRUD/archival/maintenance, record preservation, UTC projections, concurrent names/last-admin protection and retryable database lock contention.
- Chromium smoke passes: actual login/password replacement, 2 fictional labs/20 SUTs, layout/filter/sort preservation, real 30-second polling, stale/retry recovery, detail/profile.
- Local Compose smoke passes: image build, fresh migration, :5088 health/login, inventory mutation, non-root UID, SQLite integrity, migration check, and data/session retention after down/rebuild/recreate. A broken migration prevents startup. The isolated synthetic test volume is cleaned up.
- This cloud builder required its existing approved CA bundle as a transient BuildKit secret and host/proxy resolution overrides; TLS and locked package-hash verification remain enabled. No CA or credential is embedded in the image.

## Manual QA

1. Follow README local or Compose instructions, generate a local random SECRET_KEY and migrate an empty database.
2. Run CLI bootstrap, log in, confirm protected APIs/pages are gated until password replacement, then sign in again.
3. Create both labs and SUTs as a Lab Admin; verify regular users cannot mutate inventory, duplicate normalized names fail within one lab and succeed across labs.
4. Change operational condition with a reason, archive/restore an idle SUT and inspect Dashboard exclusion and state presentation.
5. As Super Admin provision/reset/disable/reactivate accounts and inspect impact/Needs attention; verify old sessions are rejected.
6. Run the supplied disposable browser/container smoke scripts; inspect actual LAN and hosted CI checks separately.

## Remaining gates

Day 2 Claim/Release/queue/reservation workflows and deadline worker are unimplemented; existing schema/test records do not establish those behaviors. Complete maintenance queue pause/resume, inactive-user FIFO eligibility, notification/desktop UI, Dashboard action modals, Detail polling and Calendar/History are still outstanding. Mixed checklist items remain unchecked. No stub coordination API is exposed and full MVP is **NOT DONE**.

Public GitHub remote-context build and a source-free Compose deployment/persistence smoke at `ee2118e2f22f4cbef80b1b991c5163b3edd0fa46` pass on the cloud Docker daemon; a newly provisioned production OS remains unverified. Actual internal server/firewall/two LAN clients, production backup/restore rehearsal and hosted CI are unverified. Set SUT_GIT_REF to a reviewed application commit before remote deployment. Full evidence and progress are in docs/implementation-status.md and TASKS.md.

## PR creation status

The implementation branch `feat/day1-foundation` has been pushed. `gh pr create` was attempted, but GitHub GraphQL returned `Forbidden`; no PR was created by that operation. Retry after GitHub API access is restored:

```bash
gh pr create --repo miragesu/sut-reservation-management --base main --head feat/day1-foundation --title "Day 1: FastAPI authentication, inventory and SQLite deployment" --body-file docs/day1-pr.md
```

Manual creation: https://github.com/miragesu/sut-reservation-management/pull/new/feat/day1-foundation
