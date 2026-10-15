# Approved Demo integration

This is the owner-approved 2026-10-16 application update, ported from the working v1.0.1 Demo rather than recreated from a prose brief. It supersedes conflicting manual attendance and Dashboard filter rules in older sections of SPEC/PLAN/AGENTS. Production storage, security and release requirements remain in effect.

## Effective behavior

- Start using explicitly creates usage. Existing `/claim` endpoints remain compatible; manual `/check-in` endpoints return 410.
- Upcoming before the booked start; Waiting for release while unavailable; Ready to start after availability and an in-app notice; In use after explicit start.
- The persisted start deadline is the earlier of notification time plus 15 minutes and the original reservation end. Previous-holder delay does not consume the window. Missing an issued deadline marks No show and frees the remaining protection, retaining records. A never-available booking completes without penalizing the owner.
- Maintenance pauses the remaining response time; resumption is still capped at the booking end. Restart does not reset the timer. Writes, notices and audit events are atomic and idempotent; reads never advance transitions.
- My SUTs combines own active usages and own reservations for every role. Cancelled reservations are excluded before counting/pagination. Legacy list URLs redirect here. Calendar remains shared; existing coordination-detail visibility is unchanged.
- Dashboard has Name/Status sorting within each Lab, Card/Table views and status colors. Sorting, modal input and layout survive polling.
- Calendar is a day/week 24-hour timeline with Lab-grouped named SUT selection, overlapping lanes, split overnight events and retained cancelled/no-show records. The current Taipei time line updates each minute only if today is in range; its translucent stroke is underneath event text. View controls reserve arrow space.
- Navigation is My SUTs, Calendar, History, Inbox, plus Admin for administrators. Labs/Inventory live under Admin. Profile is an outlined action directly left of Sign out.
- Inbox has a compact nonzero unread count, no bell or duplicate global preview. Desktop opt-in lives on Inbox; badge and delivery logic remain global. The interface is English; only notification message bodies are Chinese.
- Shared soft surfaces, borders and controls cover all pages. Body/inputs use 16px and supporting content at least 14px. Dates remain UTC at rest and Taipei at display; timezone text is stated once in the footer.

## Upgrade and recovery

Migration `c2026101601` adds nullable `ready_at`, `start_deadline` and `start_remaining_microseconds` fields. Pending legacy checked-in reservations are moved to the automatic policy; original attendance timestamps remain historical and no longer exempt expiration. Existing users, usages, queue entries and history are retained.

Stop the old application, take a verified cold backup of SQLite and the existing private configuration, then start the new single-worker image through the existing migration entrypoint. Verify health, migration head, record counts, authentication and a synthetic start/release workflow. Do not assume the old image supports the new schema. Automatic downgrade is deliberately refused: recovery restores the matching pre-upgrade backup and image together. Do not restore a backup over a live process.

This PR neither tags a release, publishes an image nor touches the production host/database. The next release must use the existing tested release workflow and immutable digest verification.

## Evidence and review

The approved Demo source was frozen with SHA-256 file hashes before porting. Runtime/private data, SQLite files, passwords and tunnel tools are excluded from the repository. UI assets/templates are carried over directly; integration changes are limited to maintainability, regression coverage, documentation and corrections documented during review.

Local validation and page-by-page comparison outcomes are recorded in `docs/demo-verification.md`. GitHub Linux CI remains the authority for installer/container checks unavailable on the Windows desktop. The full historical test suite must pass with updated assertions for the new policy; no manual-check-in assertions should be silently skipped.
