# v1.0.2 candidate release notes

Unreleased. Confirm the next unused SemVer tag before publication.

## Changes

- Replace manual attendance with automatic reservation availability, explicit Start using and persisted no-show deadlines.
- Combine personal usage and bookings into My SUTs; move shared scheduling to a real day/week Calendar.
- Preserve the owner-approved Dashboard, colored status cards and simplified Lab-grouped sorting.
- Unify readable styling and navigation across user/admin pages.
- Simplify Inbox and retain Chinese notification bodies within an English interface.
- Add a translucent minute-updated current-time Calendar marker and fix View selector spacing.

## Upgrade

Requires migration `c2026101601` and a cold backup. Pending checked-in reservations follow the new readiness policy. There is no automatic downgrade; restore the pre-upgrade database with its matching image if reverting. See `demo-integration.md` for acceptance and recovery behavior.

Release only through the existing tag-triggered workflow after the merged commit passes application, browser, installer, container and immutable-image verification. Never overwrite a published tag or image version.
