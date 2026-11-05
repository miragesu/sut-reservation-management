# CONSOLE-001 pre-release GO / NO-GO

Review date2026-11-05 (Asia/Taipei). Proposed **v1.1.0-rc.1**, not created/published.
[Readiness/evidence](rc-readiness.md), [operator checklist](production-acceptance-checklist.md),
[pilot plan](pilot-plan.md). A checked local test never authorizes production.

## Decision boundaries

| Boundary | Current decision | Required authority/evidence |
| --- | --- | --- |
| Submit this readiness PR | GO for independent review | Documentation/source inventory and honest local results; no product/release/deployment change |
| Push RC Git tag / publish RC image | **NO-GO** | R1 resolved/dispositioned with reviewed diagnostic and regression evidence; exact-source hosted CI green; owner separately authorizes exact source/version; immutable tag/registry absence rechecked; publisher/provenance/anonymous digest deployment requirements confirmed |
| Activate a real one-Client/one-test-SUT pilot | **NO-GO** | Separate scope/access authorization, verified public RC digest, C3 topology/account preflight, site-specific C4 approval and C5 independent fingerprints/custody; tested rollback and restricted pilot boundary |
| Mark actual pilot acceptance complete | **NO-GO** | Every applicable operator case executed/reviewed, C3 actual functional evidence and C4/C5 signoffs; no outstanding blocker |
| Wider Lab rollout / GA / latest or stable promotion | **NO-GO** | Separate reviewed GA source/version and stage approvals; owner/operator/security acceptance, expanded topology/capacity/recovery; existing official release or protected stable workflow only |

This session changes none of these approvals. Passing a later rerun alone does not
silently close a recorded unexplained failure. An RC image can remain default OFF
while operator acceptance is pending; artifact publishing and live activation are
separate decisions, neither authorized here.

## Artifact-release gates (all required)

- [ ] R1 participant-count validation failure has a root-cause classification,
  reviewed corrective action (or evidence-based test-environment disposition), and
  focused tests plus the complete Console runner pass on the selected source.
  Never disable auth/leases/Origin/host verification, drop assertions or mask failure
  with unlimited retries/increased waits to make release checks green.
- [ ] All required unit, lint, legacy browser, actual mock SSH/Console browser,
  source/container, image-only, installer and recovery checks are green on the
  exact reviewed RC commit. Record the earlier failure and final results honestly.
- [ ] Independent PR review and hosted CI URLs/conclusions recorded; new main HEAD
  is not silently substituted for the owner-approved release source.
- [ ] Confirm proposed v1.1.0-rc.1 remains unused remotely and registry tag absent;
  recheck immediately before a separately authorized annotated-tag push. If either
  exists, stop; never move/overwrite or silently select rc.2.
- [ ] Verify release workflow main ancestry, SemVer prerelease parser, full-SHA
  actions, scoped publisher secrets, successful checks before publish, OCI revision/
  version/source, SBOM/provenance and immutable-version refusal. No secrets printed.
- [ ] Confirm RC job skips latest (prerelease contains '-') and stable is not
  automatically dispatched. Protected dockerhub-stable reviewers/prevent-self-review
  and STABLE_PROMOTION_ENABLED need separate operator verification; not inferred.
- [ ] After authorized publication, use clean anonymous Docker config, pull the
  public index/platform digest, compare OCI source revision to the approved commit,
  and run image-only smoke **and the Console overlay** on that published digest.
  Locally built images, anonymous manifest HEAD or a pushed Git tag are insufficient.
- [ ] Confirm latest/stable remain at their prior manifest values (or absent) after
  RC publication; retain before/after audit. An explicit RC tag left by a failed
  post-push validation is not success and must not be overwritten on retry.
- [ ] Bundle reviewed Compose hashes, operator procedures, source/image/schema/key-ID
  metadata and compatible rollback image. No real DB, key, environment or inventory
  enters the public repository/release artifact.

## Live-pilot prerequisite gates (all required before contact/activation)

- [ ] Named owner/change approval for one Client and one same-Lab test SUT, two RD
  testers, harmless allowed actions, observation window and stop/rollback authority.
- [ ] C3: Client admin independently verifies fixed SSH identity/default socket/
  existing tmux+minicom/interactive shell permissions and accepts shared OS identity
  effects. No forced-command sandbox, per-SUT OS confinement or process repair claimed.
- [ ] C4: explicit site-specific HTTP/WS interception/credential/cookie/shell risk
  signoff, restricted ingress/private bind/exact Origins, complete sensitive deny
  inventory, authenticated IPC/cap/mount separation and boot-before-Docker controls.
  No insecure mode is automatically activated. WSS needs separate verified TLS path.
- [ ] C5: independent trusted fingerprints, trained approving RD/Admin, controlled
  replacement/impact/audit/incident procedure and residual malicious-RD risk acceptance.
- [ ] Backup and key custodians demonstrate independent retrieval, cold restore,
  KEK verification/rotation and compatible old-image rollback on copies. Independent
  `/run/backup` mount outside DB/KEK and no runtime backup/KEK exposure to Web.
- [ ] Pilot instance/network boundaries prevent unapproved users/equipment access
  without changing the three owner policies, fixed quota or introducing Lab CIDR
  allowlists. claim_only alone is not a pilot-SUT/user allowlist.
- [ ] Current source and candidate defaults prove coordination availability with
  no Broker or Console keyring, then any activation is a deliberate operator action.

## Immediate stop / NO-GO conditions

Wrong target or unknown/unverified Host Key; credentials sent before pin approval;
post-revocation input; RO input reaching remote SSH; stale generation/quota bypass;
secret/transcript leakage; unexpected Gateway tmux/minicom creation/termination;
unauthorized public/sensitive target reachability; unapproved HTTP exposure; missing
mount/custody/backup or DB/count/FK/integrity mismatch; automatic credential/SECRET_KEY
replacement; unexplained repeated disconnect/participant mismatch; required test
failure; incompatible schema rollback; unapproved scope or image/source mismatch.

On stop, operator fences/stops Gateway-owned attachments, preserves safe audit and
matching DB/key/config backups, and coordinates external host response separately.
Do not destroy remote sessions or production data to demonstrate rollback. No blanket
risk waiver substitutes for a failed authorization, trust or data-integrity control.

## Approval record (all pending)

Record privately: candidate source/digest/version; case IDs/evidence; technical
reviewer; release owner; operator; security/HTTP approver; Client administrator;
independent fingerprint custodian; DB/key backup custodians; approved boundary,
Taipei timestamps, rejected/remaining cases and next explicitly authorized step.
No reviewer identity, real host address or approval is fabricated by this document.
