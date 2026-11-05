# CONSOLE-001 R1 — participant pump / SQLite contention

Review date:2026-11-05 (Asia/Taipei). Base main
`69b44960c0deaab007a43eaa4afd061804a430d6`, branch
`fix/console001-r1-participants`. [Issue20](https://github.com/miragesu/sut-reservation-management/issues/20),
[RC readiness](https://github.com/miragesu/sut-reservation-management/blob/release/console001-rc-preparation/docs/console001/rc-readiness.md),
[GO/NO-GO](https://github.com/miragesu/sut-reservation-management/blob/release/console001-rc-preparation/docs/console001/release-go-no-go.md).
GraphQL issue read returned `Post "https://api.github.com/graphql": Forbidden`;
the complete public issue body was read from its HTML structured data. No issue
comment, PR creation, production connection or release operation is performed.

## Root cause and evidence

This is a demonstrated **application event-loop/SQLite lock cycle**, not a reason
to weaken the two-distinct-RD assertion or extend its5s timeout. tmux Detach/manual
reconnect is the setup, not an operation that changes participant authorization.

1. The threaded HTTP login dependency owns SQLite `BEGIN IMMEDIATE` throughout
   account verification/session creation. Its async route/dependency must resume
   on the ASGI loop before that transaction can finish/commit.
2. The Console pump runs on that same ASGI loop. Every1s it synchronously enters a
   write unit to renew durable lease metadata and read participant membership.
   If the login still owns the writer reservation, its `BEGIN IMMEDIATE` waits up
   to SQLite's existing5000ms busy timeout **on the ASGI loop**.
3. The login worker can complete, but its route cannot resume/commit while that
   loop is blocked. A transient competing write thus becomes a timeout cycle.
   Other Console pumping/renewal is stalled; independent Broker2s leases are not
   relaxed and may expire. The old pump did not catch SQLAlchemy database errors,
   so it could terminate without reporting a revoked socket. A Connected label /
   connected metadata row is not proof of a functioning pump.
4. The new RD subsequently connects and sees two connected metadata rows; the
   old writer browser receives no new participant event. Waiting longer for its
   two-RD text cannot repair the failed pump.

### Controlled reproduction

The disposable browser fixture adds **test-only** `SUT_CONSOLE_R1_LOGIN_DELAY=1.2`.
It sleeps in the existing worker-backed login for synthetic RD `uird`, while that
request's normal SQLite write reservation is held.1.2s is below the unchanged2s
Broker lease, but spans the1s metadata-refresh interval. No application delay flag,
credential logging or production test hook is added. The original participant
assertion and5s wait remain unchanged.

Four ordinary diagnostic baseline runs passed34 checkpoints each; this confirms
intermittence, not absence of the defect. A forced pre-fix run reproduced the exact
participant assertion after detach/reconnect. A prior diagnostic-development run
also failed after this stage, but its outer exception reporter attempted to inspect
Playwright after shutdown; that reporter was corrected to capture within the live
context. That incomplete diagnostic attempt is excluded from conclusive timing
comparisons and is not represented as a success.

Conclusive pre-fix sanitized observations (browser times relative to their own
page, not a shared wall clock):

| Writer page time | Event |
| --- | --- |
|19590ms|UI Reconnecting|
|19670–19686ms|New socket8, old socket7 closed1000; new generation2 Connecting|
|19793–19796ms|New generation2 state Connected **and** connected event|
|Afterward through the failed assertion|No writer participant events|

Viewer generation1 received participant count2 at relative1330,2381,3434,4494ms.
SQLite snapshot showed writer connected/gen2 and viewer connected/gen1, neither
with a close reason. Thus the writer was not merely displaying an old generation's
Connected state; membership aggregation itself could produce two. No terminal
input/output, credential, ticket, login digest, remote address or display name was
needed to distinguish these outcomes.

The focused gateway regression makes the lock order deterministic: a worker owns
the reservation; route completion is scheduled200ms later on the ASGI loop; the
live participant pump must refresh while that worker is active. **Pre-fix failed:
5.09s loop delay**. After the fix the same timer completes within the1s assertion
bound, the writer then receives two distinct RD participants, and sockets clean up.
The historical RC run had no such diagnostics, so its exact original scheduler
trace cannot be recovered retroactively; this independently reproduces the same
assertion and demonstrates a sufficient concrete application cause.

## Corrective change

`TerminalLink.participant_snapshot` executes the complete bounded SQLite
enter/proof/membership/commit-or-rollback/close unit in a worker via
`run_in_threadpool`. Only plain lease/mode/participant values return; no Session or
ORM instance crosses the await. The authorization gate remains held, generation/
login/grant/endpoint checks and duplicate-user/write-mode merge are unchanged.
SSH/IPC/streaming occurs after the transaction closes. Worker completion does not
need an ASGI callback to commit its own SQLite unit, and its context closes even
if a caller is cancelled. No separate SQLite writer or bypass is introduced.

Database errors in establishment/pumping now follow the existing generic
session_revoked/1008 fail-closed path, rather than silently killing a pump. No raw
SQL/SSH exception is sent to the browser. A focused live-socket test injects a DB
snapshot failure after Connected and asserts revocation,1008 closure and quota
cleanup. Existing cancellation/generation/revocation tests remain required.

Unchanged:2s Broker authorization lease,5s SQLite busy timeout,1s durable refresh,
per-input authorization, precommit fencing, exact Host Keys, read-only enforcement,
10-session quota, native tmux behavior, participant count2 and browser5s assertion.
No role, schema, deployment default, remote process or product feature is changed.

## Sanitized test instrumentation

`tests/console_mock/browser_lifecycle.js` runs only in disposable Playwright
contexts, never as a production static asset. It retains at most512 metadata events:
relative time, anonymous socket ordinal, approved state, generation, participant
count and close code. It ignores binary output/outbound frames, auth-flow content,
user/display names, tickets and credentials. Database diagnostics select only
session/user/state/generation/close metadata; output anonymizes IDs. No screenshots,
terminal transcripts, full frame/SQL dumps or secret-bearing exception logs.

A Node VM regression feeds malicious extra credential/display/terminal fields and
binary messages, asserts only allowlisted keys survive and the buffer remains512.
Participant diagnostics are printed at the live failure point or explicit test-only
`SUT_CONSOLE_R1_TRACE=1`; normal production browsers have no trace/diagnostic API.
CI's existing actual Console runner now uses the controlled1.2s login delay so the
known contention case is tested, rather than depending on incidental host load.

## Verification ledger

Each complete runner is one independent fixture (new DB/accounts/keys/IPC/Broker/
SSH network/Chromium); its34 checkpoints are not34 independent repetitions.

| Check | Actual result |
| --- | --- |
| Ordinary pre-fix complete Console runs |4/4 passed,34 checkpoints each; intermittent baseline|
| Controlled1.2s pre-fix Console run |FAIL at unchanged two-distinct-RD assertion; sanitized evidence above|
| Focused competing-writer test before fix |FAIL,5.09s event-loop stall|
| After fix, controlled1.2s complete Console runs |3/3 passed,34 checkpoints each|
| After fix, ordinary complete Console runs |2/2 passed,34 checkpoints each|
| Focused contention/fail-closed/diagnostic privacy regressions |3 passed,33 deselected,3.02s|
| Full pytest suite |361 passed,120.11s; existing Starlette TestClient deprecation warning|
| Three legacy Chromium runners |All passed|
| Source Docker build and container regression |Passed;5088:80, non-root/caps, migrations, persistence and cold restore|
| Source-free image-only Compose regression |Passed, including low-security-mode fixture and recovery|
| Disposable installer lifecycle regression |Passed; fresh/rerun/upgrade preserve configuration, secret and existing records|
| Ruff check/format, Prettier diagnostic fixture, actionlint, diff whitespace |Passed|

After-fix repetition1 writer trace: Reconnecting at16560ms, socket8/new generation2
at16633–16649ms, Connected at16756–16760ms, participant1 at18612ms and
participant2 at19711ms. Both synthetic RD metadata rows remained connected. This
shows the previously silent pump now resumes through the contention while retaining
the exact original participant assertion. Times are page-relative, not a cross-page
clock or an SLA. The other four independent runs also passed that assertion.

Local evidence logs are `/tmp/console-r1-after-{1..5}.log`,
`/tmp/console-r1-forced-before-evidence.log`, `/tmp/console-r1-focused-before.log`,
`/tmp/console-r1-pytest.log` and regression logs under `/tmp/console-r1-*`.
They are ephemeral local artifacts, not hosted CI or durable production records.
Only sanitized observations are retained here; no failed attempt is silently retried
into a passing result. The Phase E deployment runner also passed all seven groups: fresh Console-on
installation; identities/mount custody/private IPC/5088:80; actual namespace
firewall; populated upgrade and cold restore; compatible old-image/pre-upgrade
backup rollback; wrong-KEK rejection and independent backup recovery; absent HTTP
acknowledgement/unavailable Broker fail-closed startup.

Reproduction on a disposable local daemon (locked Python dev environment, real
Chromium, retain managed proxy/CA trust):

```sh
pytest -q backend/tests/test_console_gateway.py -k competing_sqlite_writer
pytest -q backend/tests/test_console_gateway.py -k participant_snapshot_database_failure
pytest -q backend/tests/test_console_browser_diagnostics.py
docker build --secret id=build_ca,src=/etc/ssl/certs/ca-certificates.crt \
  -t sut-console001-c:local .
SUT_CONSOLE_R1_LOGIN_DELAY=1.2 SUT_CONSOLE_R1_TRACE=1 \
  SUT_CONSOLE_BROWSER=1 SUT_BUILD_CA=/etc/ssl/certs/ca-certificates.crt \
  python scripts/console_mock_smoke.py
```

For a negative control, use base main69b4496 runtime with the same disposable fixture
instrumentation and controlled delay; do not run it against any real account/host.
The source commit/patch and private local build IDs identify before/after variants;
no RC image tag or public registry artifact is produced by these commands.

## Disposition and limits

The application fix passes five independent complete Console repetitions and the
listed regression checks. Independent review and exact-source hosted CI remain
pending; R1 is not declared production accepted by passing local runs alone. Confirm the reviewed fix and exact-source hosted
CI before updating the unmerged RC readiness gate; this branch does not merge or
rewrite the RC preparation branch. C3 actual Client/socket/shell, C4 HTTP/WS LAN risk,
C5 independent Host Key acceptance, real load/capacity and production recovery
remain separate open gates. Prolonged real DB outages/CPU/thread-pool exhaustion
must still fail closed; no guarantee of unlimited availability is made.

No company Server, Console Client, BMC, UART, production SQLite or credential is
accessed. Console enable/HTTP opt-in exists only in synthetic fixtures; operator
configuration stays OFF/claim_only/insecure HTTP false. No RC publication, tag,
Docker Hub promotion, automatic merge or live activation. ChatGPT creates and
independently reviews the PR after branch delivery.
