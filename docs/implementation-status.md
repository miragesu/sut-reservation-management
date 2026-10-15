# Implementation Status

Status: NOT STARTED

- [ ] Day 1: Docker, models, migrations, auth, Lab/SUT management
- [ ] Day 2: Claim, Release, Queue, Reservation, usage history
- [ ] Day 3: dashboard, notifications, integration tests, deployment checks

All BR-001 through BR-028 require implementation and passing acceptance tests. Target: three days, not a waiver of quality gates.

Deployment: public GitHub remote build; container port 8000 to host 5088; SQLite stored only in a persistent local Docker named volume. Production data and secrets never enter GitHub.
