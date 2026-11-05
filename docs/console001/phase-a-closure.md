# CONSOLE-001 — Phase A design closure

**Closed as a documentation/design milestone on 2026-11-05, at the owner's request.**

## Approved scope and authoritative rules

- The complete [Q1–Q83 baseline](../CONSOLE_001_REQUIREMENTS.md) is retained, including later owner-approved amendments: C2 requires **RFC1918 private IPv4** for direct BMC SSH but no per-Lab CIDR allowlist; C1 allows the fixed Console Client SSH account's full interactive shell after Detach from the automatically attached **existing** tmux session.
- The proposed high-level architecture is the basis for future **mock-only Phase B planning**: authenticated browser xterm.js/WS gateway, private non-root SSH and secret broker, independent Client and BMC target mappings, encryption and host-key checks, durable audit, scoped Web-session revocation, three access policies, maintenance grants and 10-session quota.
- Existing coordination/reservation behavior remains untouched. Console remains **disabled by default** until separately developed and approved.
- [Phase A.2 C3 disposable evidence](c3-interactive-tmux-validation.md) is integrated from research PR #14. **FEASIBLE WITH PREREQUISITES** is evidence for the tested same-account synthetic SSH/tmux model, not real Client topology, browser, WS, migrations or production.

## Closure decision and boundaries

Phase A is **COMPLETE as a design-document milestone**. It is **not** a declaration that every engineering choice is final or production/live connectors are safe. The owner request to finish Phase A authorizes merging documentation/research evidence to main. It does **not** authorize implementing Phase B, live SSH, BMC access, Console Client changes, production secrets, image publication or rollout.

Engineering proposals A1–A15 in [compatibility.md](compatibility.md) remain **provisional**, particularly A2 tmux grammar, A3/A4 broker/crypto, A8 login-session storage, A14 disabled-Client mapping-slot semantics, and A1 the unconfirmed grant revoke UX. Before each implementation increment, Codex must identify relevant assumptions, validate them with synthetic tests, and obtain design review. Do not represent proposals as owner-numbered decisions.

## Deferred gates for later phases

| Gate | Status after Phase A | Requirement before use |
| --- | --- | --- |
| C1 — Client shell policy | **Owner-resolved** | Test interactive login and Detach-to-shell when implemented; no forbidden tmux confinement requirement |
| C2 — BMC IPv4 classes | **Owner-resolved** | Implement/test RFC1918-only, sensitive/self denial, fixed SSH port 22 and no Lab CIDR list |
| C3 — actual Client topology | **Mock-feasible; production unverified** | Review account privileges, socket ownership/ACL, tmux/minicom, shared effects and shell startup on authorized representative Client |
| C4 — HTTP/WS risk | **Intranet exception approved; operator signoff pending** | Explicit CONSOLE_ALLOW_INSECURE_HTTP=true, restricted ingress, disclosure, operator acknowledgement and transport tests; plaintext is not secure |
| C5 — RD Host Key trust | **Policy approved; pilot process pending** | Independently verifiable fingerprints, old/new comparison, audit and revocation tests, risk signoff |

No CI claim is made for unimplemented browser/WS/Broker/SQLite migrations, secret encryption or real SUT. 30/30 ×2 mock observations mean the same 30 cases repeated, not 60 unique tests.

## Handoff protocol

A future Phase B proposal must read this file and the requirements, compatibility, architecture, contracts, security, data model and acceptance matrix. Phase B begins only on a **separate explicit development instruction**, a new branch, mock-only with Console off. Live C/D/E and production gate approvals are independent. C3 harness is testing evidence, not deployed functionality.

## Change log

- 2026-11-05: Owner chose RFC1918-only BMC targets without Lab allowlist.
- 2026-11-05: Owner authorized ordinary interactive Console Client shell after tmux Detach.
- 2026-11-05: C3 two-run disposable 30-case evidence integrated from PR #14.
- 2026-11-05: Owner explicitly requested closing Phase A design milestone.
