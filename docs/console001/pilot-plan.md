# CONSOLE-001 staged pilot plan

**PLANNED ONLY. No pilot, real connection, insecure-mode activation or deployment
is authorized/executed by this RC preparation.** Review date2026-11-05, Asia/Taipei.
[Readiness](rc-readiness.md), [checklist](production-acceptance-checklist.md),
[GO/NO-GO](release-go-no-go.md), [operator procedures](operator-runbook.md).

## Scope and stop authority

Start with **one named authorized Console Client and one named authorized test
SUT in the same Lab**, one pre-existing default-socket tmux/minicom path, one fixed
reviewed SSH identity, two approved test RD plus the Client/operator administrators.
No actual identifiers/IPs/passwords belong in this public plan. Use test accounts
and synthetic output. BMC step is optional until independently authorized for that
same test SUT; no discovery scan or automatic alternate endpoint probing.

Before connection, owner records a private scope/time window, C3 account/socket
preflight, C4 transport/network risk approval, C5 independent fingerprints and
named operator/rollback authority. Actual functional results remain pending until
the authorized pilot runs; prerequisite approval does not invent a PASS result.
Any tester may stop input; operator may stop Web/Broker and fence Console. Never
kill remote tmux/minicom or force-release coordination records as a stop mechanism.

Current software has no dedicated pilot-user or pilot-SUT activation allowlist.
claim_only is not a pilot-scope security boundary: active Admins and RD mappings/
Host Key authority remain owner-approved. Enforce the narrow pilot with a separate
operator-controlled pilot instance/synthetic DB (any real-data copy needs separate
privacy/custody approval), restricted
inbound access from approved test workstations and a deny-policy/firewall topology
which routes only authorized test equipment. Do not modify policy definitions or
invent Lab CIDR allowlists. If separation cannot guarantee the pilot boundary,
NO-GO; additional controls need their own reviewed scope, not an ad-hoc bypass.

## Stage0 — paper review and isolated RC evidence

Owner/reviewer: approve this documentation; resolve the recorded browser validation
failure, review exact-source hosted CI and all local checks. Reserve proposed
v1.1.0-rc.1 only after rechecking remote tags/manifests; no tag is created here.
A separate release authorization must publish the RC and anonymously validate its
fixed digest/provenance/Console deployment before any operator pull.
Exit: reviewed candidate with no open release blockers, immutable evidence manifest,
no latest/stable movement, rollback image/backup and named custodians identified.

## Stage1 — operator preflight, Console still OFF

On a separately approved pilot host/instance, verify the mounted /data identity,
space/modes, current backup/restore rehearsal, fixed RC digest and all service
privilege/mount/namespace boundaries. Prove coordination works without Broker/keys
using the base image-only configuration. Review private host/container deny list,
restricted ingress and boot-before-Docker ordering. Client admin verifies existing
processes/default socket/account shell rights locally without Gateway changes.
Exit: checklist C3-01..03, C4 preflight, C5-01 and DATA prerequisites approved.
Any need to repair a real tmux process/credential/ACL is a separate change request.

## Stage2 — bounded UART pilot

After explicit site approval, operator deliberately applies the approved policy
(initially claim_only), exact Origin, independent custody and transport settings.
HTTP/WS requires its own plaintext risk record and exact attestation; HTTPS/WSS
requires separately tested trusted termination. This plan does not set either.

Creating Admin verifies Client fingerprint independently, validates password/key
before save and maps only the approved existing session. Claim holder/Admin proves
RW; unauthorized RD denied. With a separately approved temporary policy/grant test,
prove two writers, read-only boundaries, participant deduplication, native Detach-to-
shell and peer-preserving Disconnect. Restore claim_only. Exercise missing session,
wrong credentials, lost network, manual fresh Connect and no replay. Do not use
hardware power/firmware operations or destructive tmux commands to demonstrate shell.
Exit: C3 actual function evidence, scoped authorization/quota/UI checklist results,
no secrets/transcripts, remote original processes/external clients preserved.

## Stage3 — same-SUT BMC, revocation and recovery

Only after additional BMC authorization, verify RFC1918/fixed22 and independent BMC
pin, fresh credentials/attempt limits and transport switching. Use approved test
services to prove egress denials without contacting real sensitive destinations.

Perform controlled mapping/credential/pin replacement with independently supplied
pins and affected-session confirmation; prove UART/BMC revocation scope, Claim/
maintenance grant expiry/Normal transition/account changes and no auto-reconnect.
Use copied synthetic pilot data for cold restore, wrong-key failure/independent key
recovery and compatible old-image rollback. Never rehearse by overwriting production
DB, live pins, user credentials or remote processes.
Exit: all relevant checklist cases PASS with reviewed evidence and tested rollback.

## Stage4 — observation and independent acceptance

Proposed observation window: one approved working day, including at least one
planned reconnect and maintenance-grant expiry; operator sets the actual window
and explicitly accounts for longer login/24h-bound cases via isolated clock tests
or separately authorized extended observation. This is not a new idle cutoff or
SLA. Observe metadata-only failures, health, output/backpressure, participant/quota,
revocation latency, CPU/memory and coordination deadlines. Do not record terminal
payloads or loosen2s leases to mask overload. Any untested long-duration gate stays
NOT RUN and blocks the corresponding acceptance claim.

Stop immediately for wrong target, unverified Host Key, post-revocation input,
unauthorized RO writes, secret exposure, unexpected process creation/termination,
data mismatch, missing mount, failed backup/keys or repeated unexplained disconnect.
Revert transport/Console settings only via reviewed operator change; preserve audit,
new DB and matching recovery material. Coordinate separately if an authorized shell
user started remote processes; Gateway shutdown cannot undo them.

## Stage5 — deliberate expansion

After C3/C4/C5 and all pilot signoffs, owner may authorize a **new** stage for a second
SUT on the same Client, then another Client, then another Lab. Recheck exact account/
socket, same-Lab binding, distinct Client fixed identity, OOB pins, sensitive inventory,
capacity/shared-shell consequences and per-stage backup/rollback. Do not treat one
Client's success as evidence for all real BMCs/custom sockets or as authorization
to enable all_authenticated globally. No expansion, GA release, latest/stable promotion
or automatic merge follows from this document or from passing synthetic tests.
