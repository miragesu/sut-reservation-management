# Demo integration verification

Base: v1.0.1 / `2755a3ee68e30db75f468607fd3ff1e681fc7765`, also the remote main at integration start.

- Approved Demo source snapshot and hashes retained locally outside the source checkout.
- First complete Windows run exposed superseded check-in/timezone expectations. Those assertions were rewritten to exercise availability-based expiry, persisted readiness and removed check-in rather than disabled.
- Application/coordination tests: 205 passed in the second complete run; 8 installer checks require Linux facilities or LF checkout behavior absent in Git Bash on Windows. Those checks remain enabled for Linux CI.
- Ruff checks pass after formatting the ported Python additions.
- Fresh migration, schema consistency, guarded downgrade and live-record preservation are covered by the regression suite.
- Browser smoke, multi-user workflows, desktop-notification fallbacks and visual parity verification are in progress; final results will replace this paragraph before the PR is merged.

No company data, production host or production database was used. Test credentials and database snapshots are local-only and excluded from commits.
