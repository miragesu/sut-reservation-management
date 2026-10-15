"""One periodic task in the supported one-worker SQLite deployment.

Transactions also make overlapping runs/restarts safe: transition and notification
identities are persisted atomically, not tracked in process memory.
"""

import asyncio
import logging

from app.core.database import unit_of_work, utcnow
from app.services.coordination import reconcile_all

logger = logging.getLogger("sut.deadlines")


def process_deadlines(engine, clock=utcnow):
    with unit_of_work(engine, write=True) as db:
        reconcile_all(db, clock())


async def run_deadlines(app, stopped):
    while not stopped.is_set():
        try:
            await asyncio.to_thread(process_deadlines, app.state.engine, app.state.clock)
            app.state.deadline_last_success = app.state.clock()
        except Exception:
            # No request payloads, SQL parameters or credentials in logs. The next
            # bounded iteration retries the whole rolled-back transaction.
            logger.error("Deadline transaction failed; retrying on next interval")
        try:
            await asyncio.wait_for(stopped.wait(), timeout=app.state.settings.deadline_poll_seconds)
        except TimeoutError:
            continue
