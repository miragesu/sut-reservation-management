# CONSOLE-001 Phase A design review

Status: **PROPOSED / OWNER REVIEW REQUIRED / NO IMPLEMENTATION**.
Base: `1536ea7b72dc32e8e0f11c8df3f0c7896e04691a` (latest fetched main).
The complete [owner baseline](../CONSOLE_001_REQUIREMENTS.md) is authoritative:
Q1–Q83, topology, three Compose policies, and explicit intranet HTTP/WS exception.
This package does not replace or amend that ledger. Proposed engineering choices
and unresolved conflicts are marked separately; none is a new owner decision.

| Document | Review purpose |
| --- | --- |
| [Architecture](architecture.md) | Components, authorization, lifecycle, quota and mutation/revocation ordering |
| [Schema and migration plan](data-model.md) | SQLAlchemy entities, SQLite invariants, preservation and recovery |
| [Security threat model](security.md) | Secrets, trust, SSRF, tmux, HTTP exception and deployment boundaries |
| [Interface contracts](contracts.md) | Proposed HTTP, WebSocket, errors, limits and secret boundaries |
| [Acceptance and milestones](acceptance.md) | Q1–Q83 traceability, fixtures, Phases B–E and rollout gates |
| [Compatibility and review register](compatibility.md) | Explicit old/new scope conflicts, internal ambiguities and assumptions |
| [Phase A verification](verification.md) | Checks actually run, review status and delivery evidence |

Read these together. All endpoints, tables, dependencies, flags and numerical
resource budgets below are **planned**, not present runtime behavior. No Python,
JavaScript, migrations, dependencies, image, installer, Compose or secrets are
changed in Phase A. No SSH, terminal, external host probe or production pilot runs.
The existing coordination UI and approved Demo behavior remain unchanged.

Phase B is ready for **reviewed, mock-only foundation work after approval of this
scope amendment**, not live connectivity. C1/C2/C3 in the review register block
live connector approval. No production readiness is asserted by documentation or
by the existing application's historical passing tests.

The pre-existing remote draft `06d23f8` is preserved as a merge parent. Its schema/
validation entry paths redirect to the consolidated package; alternatives and
unresolved differences are recorded in the [reconciliation register](compatibility.md#reconciliation-of-the-existing-remote-draft).
No owner baseline or remote commit was overwritten.
