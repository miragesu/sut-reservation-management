# Proposed SQLAlchemy schema and Alembic plan

Design only. No models or revisions are implemented. Reuse existing integer Lab,
SUT and User IDs, `Base` naming conventions and UTCDateTime. SQLite stores UTC
naive representation with aware UTC boundaries; UI uses Asia/Taipei. New tables
use integer PKs unless an explicit opaque token/security UUID is specified.
All retained entity FKs use RESTRICT, with no delete-orphan/cascade history deletion.
See [architecture](architecture.md), [security](security.md), [contracts](contracts.md).

## Entities

| Planned entity | Fields and invariants |
| --- | --- |
| `ConsoleClient` / `console_clients` | id; stable random `security_id` UUID UNIQUE for encryption binding; lab_id FK; required name/normalized_name; canonical IPv4 UNIQUE globally including Disabled; ssh_port int CHECK1..65535 default22; ssh_username (admin projection only); auth_method enum password/private_key; active_credential_id; enabled; notes; metadata_version and connection_epoch; created/updated UTC and actors. UNIQUE(lab_id,normalized_name). No delete endpoint. Name/notes do not bump connection_epoch. |
| `ConsoleCredential` / `console_credentials` | id; opaque credential UUID UNIQUE; Client owner security UUID FK; method; ciphertext, nonce, wrapped_data_key, wrap_nonce, algorithm/schema version, key_id, crypto_revision, SSH credential generation, created/replaced times and actor. Only encrypted secret bundle contains password or private key/passphrase. No decrypt/reveal API. Active ref replaced atomically; old generation marked replaced, never silently used as fallback. Crypto rewrap is separate from SSH generation. |
| `ConsoleUartMapping` / `console_uart_mappings` | sut_id PK/FK; client_id nullable FK; tmux_session nullable; revision; endpoint_epoch; materialized active_slot boolean; updated actor/time. Both Client/session null (Not Configured) or both present. Case-sensitive tmux identity, proposed ASCII `[A-Za-z0-9_][A-Za-z0-9_-]{0,63}` with exact-match target; backend validation shared by every write path. No ttyUSB inventory prerequisite. |
| `ConsoleBmcEndpoint` / `console_bmc_endpoints` | sut_id PK/FK; canonical IPv4 nullable; revision; endpoint_epoch; updated actor/time. No configurable port column: only22; API rejects supplied port. No username/password fields. Independent from legacy `suts.bmc_ip` and `host_ip` inventory; do not auto-import potentially IPv6/untrusted inventory targets or grant RD inventory administration. |
| `ConsoleHostKey` / `console_host_keys` | id; exactly one owner Client FK or BMC endpoint FK (XOR CHECK); target IPv4, port, endpoint identity epoch; key algorithm and public wire blob; SHA256 fingerprint; trust_revision; accepted/replaced times and actor; previous key ref. Public key is not a private key. Partial unique index permits one current trust record/owner; superseded trust retained. BMC trust never follows an IP remap implicitly. |
| `ConsoleMappingEvent` / `console_mapping_events` | id; SUT FK; transport; actor FK; UTC; old/new safe endpoint snapshots and revision; optional reason; audit_event_id. Append-only, no restore endpoint. Readable by active authenticated RD, retained on archive. No SSH credential, BMC username/password or terminal bytes. |
| `ConsoleGrant` / `console_grants` | id; user_id/SUT/admin FKs; created_at, expires_at, reason optional; state active/expired/revoked; closed_at, close reason; revision. CHECK expires_at>created_at AND expires_at<=created_at+24h (SQLite julianday equivalent plus service aware-UTC checks). Initial duration one of1/2/4/8/12/24h. Partial UNIQUE(user_id,sut_id) WHERE state=active. State returning Normal permanently revokes; no auto renewal or notification. |
| `ConsoleSession` / `console_sessions` | id opaque UUID; actor User/SUT FKs; transport; login_session_digest (indexed opaque historical binding, **not FK** to short-lived LoginSession); slot nullable1..10; state reserved/connecting/connected/reconnecting/closed; RO/RW; instance_id; attachment_generation; endpoint/Client/credential/trust epochs; authorization sources incl grant_id/usage_key; created/connected/closed_at, lease_until, safe close reason. UNIQUE(user_id,slot) for nonnull slots; CHECK active states require slot, closed requires null. Never persist terminal content or direct BMC identity. |
| `ConsoleTicket` / `console_tickets` | id; SHA256 token digest UNIQUE; session_id; login digest; actor; normalized Origin; endpoint/attachment epochs; expires_at; used_at. No raw token. Single-use CAS inside write reservation; stale/multiple socket redemption rejected. This is security metadata, not a browser bearer in a URL. |
| `ConsoleAuthFlow` / `console_auth_flows` | id opaque; session/actor/login binding; generation; attempt_count CHECK0..3 for BMC; in_flight boolean; lease/expiry/closed status. Holds bounded auth attempt accounting, not username/password. Credential candidate/validation evidence is RAM-only. Expired flow cannot be resurrected by another socket. |
| `ConsoleRevocation` / `console_revocations` | id; unique logical event key; affected session/generation and target epoch; reason enum; created/delivered time. Durable outbox committed with mutation/audit, not terminal data. Idempotent delivery and fencing. |

Existing `audit_events` can retain safe Console lifecycle/credential/grant/trust
metadata with an explicit serializer (today `audit(**details)` is too permissive
for secret-bearing payloads). Add append-only events for grant extension, expiration,
trust before/after, auth success/failure, connection/disconnection and system cleanup.
If an event stores counts, do not store participants' full user models or credentials.
No terminal transcript, per-writer lease, saved font/search, or session output table.

LoginSession rows are deleted by existing logout/password/reset/pruning paths.
A RESTRICT FK from retained ConsoleSession would break them; instead store the
opaque digest and explicitly re-resolve its live row on every authorization.
Never expose that digest in UI/API/audit. User/SUT attribution remains retained.

## Relational and concurrent invariants

- SQLAlchemy partial Index on `(client_id,tmux_session)` with
  `sqlite_where=active_slot=1` enforces one **active** UART binding, not uniqueness
  of names globally. `active_slot = configured AND NOT sut.is_archived AND
  client.enabled`; derived field is never accepted from an API payload.
- The alternative prior-draft interpretation retains a disabled Client binding's
  unique slot; see A14. This materialized-slot recommendation is not settled owner
  policy. Phase B must resolve it before implementing triggers/reenable behavior.
- SQLite triggers for new mapping insert/update and Client Lab updates enforce
  `Client.lab_id == SUT.lab_id`. SUT Lab is already immutable via service; defensive
  trigger rejects a raw incompatible move. This avoids rebuilding existing SUTs
  merely to add composite foreign keys in the first migration.
- Triggers/service hooks synchronize active_slot on archive/restore and Client
  disable/reactivate. Restoring a conflicting retained mapping fails409 with the
  conflicting SUT, never steals or silently clears another mapping. Client reenable
  rechecks all slots atomically; conflict leaves it disabled. A disabled Client
  cannot be newly selected even though its existing bindings remain visible.
- Client Lab move checks **all retained bindings**, including disabled/archived
  ones. List incompatible SUTs for manual clear/reassignment; no cross-Lab exception.
  Lab deletion with retained Clients returns409 even if no SUTs remain.
- Proposed archived mapping behavior: history/edit/clear remains available to active
  RD, but slot remains inactive and all Connect/grant operations are denied until
  restoration. No implicit restoration by editing. This is review assumption A6.
- Client canonical IPv4 UNIQUE includes disabled records across Labs and ports.
  Name normalization is trim+casefold, exactly like SUT naming; tmux names instead
  retain exact case. Addresses are strict dotted-quad, no hostnames/IPv6/octal.
- Grant active uniqueness uses a materialized terminal state; time is not a partial
  index expression. Sweep/next write first expires prior due grants and audits once,
  then fences old grant-dependent leases before inserting a new grant; a fresh grant
  cannot resurrect a logically expired attachment. GET derives effectiveness without writes. Extend only
  before expiry, keep original created_at, increase expiry but never exceed24h.
- Quota allocation under BEGIN IMMEDIATE finds a free numbered slot1..10; unique
  user/slot is the final guard against concurrent eleventh sessions. Reconnect uses
  same row/slot with incremented attachment generation. Old-close CAS cannot free
  a newer attachment. Closed history remains with slot=NULL.
- Rows pin connection epoch rather than only a mutable display-name version. Notes
  edits do not force disconnect. All epoch changes and durable revocation/audit
  are in one transaction. Freeze/SSH proof happens **outside** this transaction.
- Initial Client create allocates a security UUID in RAM, verifies trust and SSH
  authentication, and encrypts the candidate outside DB locks using that UUID in
  AAD. Only then insert Client+credential+trust+audit in one transaction and bind
  active credential ref; any collision/rollback leaves no Client/secret record.
  Client ID is assigned only on insert. Failure audit may exist without a Client
  entity; it contains no candidate credential, so Q71 does not suppress audit.

## Planned migration (Phase B, not executed here)

Proposed revision name `console001_b01`, down_revision `c2026101601`; verify the
actual Alembic head before implementation and never silently branch migrations.

1. Take a stopped-writer cold backup and matching configuration/image; preserve
   WAL/SHM and ownership. Check integrity/FKs and baseline counts first.
2. Add new Console tables/constraints/indexes/triggers only. Do not rewrite or
   delete existing labs/users/SUTs/usages/queue/reservations/history. No fake
   Client rows, key material or credentials; existing SUTs start Not Configured.
3. Do not import `suts.bmc_ip` automatically or reset sessions/passwords. Feature
   stays off. New FK references do not cascade to existing business records.
4. Test fresh and populated upgrade, retained IDs/UTC/Argon hashes, old usage keys,
   queues/offers, reservation readiness deadlines and history; unchanged business
   counts and existing suite must pass with Console off.
5. Compare metadata/Alembic check; PRAGMA integrity_check / foreign_key_check;
   contention fixtures for duplicate IP, Client/name, active pair, quota and grants;
   rollback a failed final validation and prove old records/links unchanged.
6. Any downgrade after Console history/credentials/grants exist must refuse
   destructive automatic removal. For an empty new schema only, test an explicitly
   reviewed reversal. Normal rollback uses matching pre-upgrade backup + prior
   image + independent keyring, never overlay live SQLite/WAL or old image on a
   newer schema. New writes require reconciliation before rollback acceptance.

BMC target IPv4 is not globally unique across SUTs: the owner imposes global IPv4
uniqueness on Clients only. Multiple SUT endpoint records may intentionally point
to the same BMC; warn safely if useful, do not invent a uniqueness rejection.

## Backup, retention and recovery

SQLite backup contains encrypted Client secret bundles, public host-key history,
endpoint revisions, grant/audit history and session metadata. It is still sensitive
inventory, not publishable data. Root keyring is stored/backed up separately with
all key IDs needed by retained backups; `SECRET_KEY` is a different secret and
must also be preserved securely for application recovery. See [key rotation](security.md).
No terminal content can be recovered because none is persisted.

Recovery rehearsal restores a compatible image/SQLite backup into an empty isolated
directory, supplies matching independent keyring separately, checks all record
counts/FKs/epochs, proves secret decryption without showing it, tests login and mock
SSH host pin/auth, and marks old instance leases/tickets terminal. It must not
reopen prior SSH sessions or replay input. Missing/wrong key fails closed for
Console, never generates a replacement key and overwrites ciphertext. A changed
remote credential may require out-of-band reprovisioning despite a valid old backup.

Session/ticket/auth-flow expiry cleanup is separate from indefinite business Usage
History. Retention periods for terminal-free Console metadata, old ciphertext and
audits require review (A10); baseline design keeps histories, never purges existing
MVP records. Expired bearer digests can be removed after a reviewed security TTL;
that is not a terminal recording or history restore facility.
