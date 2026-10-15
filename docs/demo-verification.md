# Demo integration verification

Base: v1.0.1 / `2755a3ee68e30db75f468607fd3ff1e681fc7765`, also the remote main at integration start.

- Approved Demo source snapshot and hashes retained locally outside the source checkout.
- First complete Windows run exposed superseded check-in/timezone expectations. Those assertions were rewritten to exercise availability-based expiry, persisted readiness and removed check-in rather than disabled.
- Application/coordination tests: 205 passed in the second complete run; 8 installer checks require Linux facilities or LF checkout behavior absent in Git Bash on Windows. Those checks remain enabled for Linux CI.
- Ruff checks pass after formatting the ported Python additions.
- Fresh migration, schema consistency, guarded downgrade and live-record preservation are covered by the regression suite.
- All three Chromium suites pass locally: mandatory password change and profile, Dashboard sorting/layout/polling, multi-user start/release/FIFO/reservations/maintenance, and notification permission/fallback/read workflows. Native date fields use minute-format input and Windows subprocess/database handles are explicitly closed.
- Seventeen authenticated pages were compared at 1536px desktop and 390px mobile against the frozen approved Demo, using identical synthetic database snapshots and a fixed clock: initially **34/34 screenshots were pixel-identical**. Final rerun after the equipment-name regression fix: **33/34 byte-identical; the remaining mobile History screenshot differs only in six native-input border pixels by one RGB level** (no text, layout or geometry difference). Compared pages: Dashboard, My SUTs, new reservation, Calendar, History, Inbox, Profile, change password, SUT detail, reservation detail, Admin, Labs, Inventory, register SUT, edit SUT, accounts and account detail. The candidate/reference servers were local-only; production and the running Demo were untouched.
- Read-only calendar tooltips now retain operational reason/current-use context; this restores existing coordination information without changing the visible approved layout.
- Self-review found and fixed a translation edge case: an equipment name containing `Claim` must not be translated into `Start using`. Added a regression test. Added repo-level own-data/query-scope, cancelled counting, shared Calendar, navigation/redirect and Inbox placement tests.
- Final PR checks must include the Linux installer and container smoke jobs before merge. No release tag or image was published by this integration.

No company data, production host or production database was used. Test credentials and database snapshots are local-only and excluded from commits.

The first Linux container rehearsal exposed an old-policy fixture that aged only booking start and expected an immediate no-show. The container scenario now first asserts a persisted readiness deadline and exactly one availability notice, then ages that issued window to verify offline/live expiry and restart idempotency. Application source was unchanged by this test correction.
