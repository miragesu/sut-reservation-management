## Behavior

Completes the remaining Day 3 coordination UI: both Dashboard layouts use accessible Claim/Queue/Reserve/Detail modals with retained input, explicit conflict acknowledgement and immediate shared-state refresh. Adds a persistent notification bell, full unread count, paginated history, scheduled/start reminders and opt-in desktop alerts with HTTP/unsupported/denied fallback and generic contact-free bodies. Existing Day 1/2 service authorization, SQLite serialization, manual handoff and background deadline behavior remain intact.

Includes DEP-006: Host 5088 → Container 80, Uvicorn 0.0.0.0:80 and matching image healthcheck. Non-root UID 10001 retains zero capabilities/no-new-privileges; a private-container-network sysctl permits port 80 while port 79 stays privileged. Public Remote Build and SQLite named-volume architecture are retained.

Adds responsive inventory/calendar/navigation improvements, five acceptance cases, multi-user Chromium modal/platform checks, and a cold-backup restore into a separate empty disposable Docker volume. Full BR-001–BR-028 evidence is in `docs/day3-verification.md`; actual delivery results are in `docs/implementation-status.md` and `TASKS.md`.

## Verification

- 103 pytest cases pass; Ruff, format, compile and JavaScript syntax checks pass.
- Baseline, Day 2 and Day 3 actual Chromium workflows pass, including real 30-second polls, modal input retention, FIFO/manual Claim, conflicts, both layouts, mobile/keyboard and notification permission/deduplication.
- Disposable local Linux Compose passes migrations, port 5088, login/non-root, persistence after rebuild/recreate, offline/live deadlines, restart dedupe and separate-volume backup/restore integrity/session/history checks.
- Public source-free GitHub Remote Build **PASS** at `eb17c6f7dd4581caff9502e64701de6ab895fc62`, including actual **Host 5088 → Container 80**, non-root/zero-capability assertions, Chromium UI, background processing, persistence and independent-volume backup/restore.
- Hosted Actions **PASS** at final application SHA `eb17c6f`: https://github.com/miragesu/sut-reservation-management/actions/runs/38736460114 (4m 51s). Actual company LAN/production-host checks and owner acceptance remain unverified, so full-MVP production acceptance is NOT DONE.

No production data, secrets or hardware access control is added. No schema migration is needed for these UI/projection changes; existing fresh and populated migration tests remain in the suite.

Refs #4. Application implementation alone does not establish LAN deployment acceptance; the remaining external gates require project-owner review.
