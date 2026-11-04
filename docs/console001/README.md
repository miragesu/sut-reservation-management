# CONSOLE-001 Phase A design package

Status: PROPOSED DESIGN / OWNER REVIEW REQUIRED / NO CONSOLE IMPLEMENTATION.

Base main: `1536ea7b72dc32e8e0f11c8df3f0c7896e04691a` (2026-11-05 inspection).
Read [the complete authoritative requirements](../CONSOLE_001_REQUIREMENTS.md) first. Its 83 decisions and unnumbered policies remain unchanged. This package is self-contained and does not depend on chat history.

| Document | Review purpose |
|---|---|
| [Architecture](architecture.md) | Components, trust boundaries, policies, lifecycle, concurrency |
| [Schema and migrations](schema.md) | Proposed SQLAlchemy entities, SQLite invariants and preservation |
| [Security](security.md) | Threat model, credentials, host trust, HTTP exception, residual risk |
| [Contracts](contracts.md) | Proposed HTTP, broker and WebSocket interfaces |
| [Compatibility and assumptions](compatibility.md) | Explicit scope amendment, conflicts and unresolved engineering gates |
| [Acceptance and milestones](acceptance.md) | Q1–Q83 traceability, B–E milestones, fixtures, rollout gates |
| [Validation](validation.md) | Documentation-only verification and limits |

Owner-confirmed requirements are identified by Q number or requirements section. Exact schema, protocol, limits other than fixed owner values, dependency selection and isolation topology are engineering proposals, not additional owner decisions. Approval of this documentation is not production deployment authorization. Phase B can prepare isolated foundations only after design review; Phase C live attachment remains blocked by the helper and network proof obligations.

Current implementation observations: `backend/app/core/dependencies.py` requires an HTTP Request, validates a hashed `LoginSession` and gates mandatory password change; it cannot simply be reused unchanged as a WebSocket dependency. `database.py` uses `BEGIN IMMEDIATE`, WAL and short synchronous sessions. `main.py` supplies HTTP-only security headers, a 12-hour default login lifetime and a background coordination deadline task. `domain.py` already has `SUT.bmc_ip` (inventory IPv4/IPv6), not a Console trust identity. `inventory.py` restricts SUT edits to admins and refuses SUT Lab changes. Current Alembic head is `c2026101601`; no Console tables/routes/settings/dependencies exist. These are integration points, not evidence that Console works.
