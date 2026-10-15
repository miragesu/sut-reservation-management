## Behavior

Completes the remaining Day 3 coordination UI: both Dashboard layouts use accessible Claim/Queue/Reserve/Detail modals with retained input, explicit conflict acknowledgement and immediate shared-state refresh. Adds a persistent notification bell, full unread count, paginated history, scheduled/start reminders and opt-in desktop alerts with HTTP/unsupported/denied fallback and generic contact-free bodies. Existing Day 1/2 service authorization, SQLite serialization, manual handoff and background deadline behavior remain intact.

Adds responsive inventory/calendar/navigation improvements, five acceptance cases, multi-user Chromium modal/platform checks, and a cold-backup restore into a separate empty disposable Docker volume. Full BR-001–BR-028 evidence is in `docs/day3-verification.md`; actual delivery results are in `docs/implementation-status.md` and `TASKS.md`.

## Verification

- 103 pytest cases pass; Ruff, format, compile and JavaScript syntax checks pass.
- Baseline, Day 2 and Day 3 actual Chromium workflows pass, including real 30-second polls, modal input retention, FIFO/manual Claim, conflicts, both layouts, mobile/keyboard and notification permission/deduplication.
- Disposable local Linux Compose passes migrations, port 5088, login/non-root, persistence after rebuild/recreate, offline/live deadlines, restart dedupe and separate-volume backup/restore integrity/session/history checks.
- Published pinned-SHA GitHub Remote Build: result recorded in implementation status before handoff.
- Hosted Actions and actual company LAN/production-host checks are reported separately; no full-MVP production-ready claim is made before these external gates and owner acceptance pass.

No production data, secrets or hardware access control is added. No schema migration is needed for these UI/projection changes; existing fresh and populated migration tests remain in the suite.

Refs #4. Application implementation alone does not establish LAN deployment acceptance; the remaining external gates require project-owner review.
