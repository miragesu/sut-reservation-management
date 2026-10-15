"""Day 2 assertions used only in container_smoke's random disposable Compose project."""

import secrets
import time
from contextlib import ExitStack
from datetime import UTC, datetime, timedelta

import httpx


def check_coordination(client, mutation, run, ready, lab):
    with ExitStack() as stack:
        users = {}
        for username in ("smoke-first", "smoke-next"):
            initial = secrets.token_urlsafe(24)
            replacement = secrets.token_urlsafe(24)
            response = mutation(
                client,
                "POST",
                "/api/v1/users",
                {
                    "username": username,
                    "display_name": "Synthetic " + username,
                    "team": "Demo",
                    "email": username + "@example.com",
                    "temporary_password": initial,
                    "role": "user",
                },
            )
            assert response.status_code == 201, response.text
            session = stack.enter_context(httpx.Client(base_url="http://127.0.0.1:5088", trust_env=False))
            assert (
                mutation(
                    session, "POST", "/api/v1/auth/login", {"username": username, "password": initial}
                ).status_code
                == 200
            )
            assert (
                mutation(
                    session,
                    "POST",
                    "/api/v1/auth/change-password",
                    {"current_password": initial, "new_password": replacement},
                ).status_code
                == 204
            )
            assert (
                mutation(
                    session, "POST", "/api/v1/auth/login", {"username": username, "password": replacement}
                ).status_code
                == 200
            )
            users[username] = session
        first, following = (users[n] for n in ("smoke-first", "smoke-next"))
        sut = mutation(
            client,
            "POST",
            "/api/v1/suts",
            {"lab_id": lab, "name": "Synthetic Coordination SUT", "platform": "Demo", "owner_team": "Demo"},
        ).json()["id"]
        usage = mutation(
            client,
            "POST",
            f"/api/v1/suts/{sut}/claim",
            {"duration_minutes": 60, "purpose": "Synthetic Docker usage"},
        )
        assert usage.status_code == 201, usage.text
        usage = usage.json()
        for session in (first, following):
            assert (
                mutation(
                    session, "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": 60}
                ).status_code
                == 201
            )
        assert (
            mutation(
                client, "POST", f"/api/v1/suts/{sut}/release", {"usage_key": usage["usage_key"]}
            ).status_code
            == 200
        )
        now = datetime.now(UTC)
        booking = mutation(
            client,
            "POST",
            "/api/v1/reservations",
            {
                "sut_id": sut,
                "start_time": (now + timedelta(hours=1)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
                "purpose": "Synthetic restart deadline",
            },
        )
        assert booking.status_code == 201, booking.text
        booking_id = booking.json()["id"]
        # Stop the service before changing only synthetic timeline data. Startup must
        # catch up atomically from the same named volume, without a browser or GET.
        run("stop", "sut-management")
        shift = (
            "import sqlite3; from datetime import datetime,UTC,timedelta; "
            "c=sqlite3.connect('/app/data/sut.db'); n=datetime.now(UTC).replace(tzinfo=None); "
            f"c.execute('UPDATE queue_entries SET notified_at=?,offer_expires_at=? WHERE sut_id=? AND offer_status=\\'notified\\'',((n-timedelta(minutes=16)).isoformat(' '),(n-timedelta(minutes=1)).isoformat(' '),{sut})); "
            f"c.execute('UPDATE reservations SET start_time=?,end_time=? WHERE id=?',((n-timedelta(minutes=20)).isoformat(' '),(n+timedelta(hours=1)).isoformat(' '),{booking_id})); c.commit()"
        )
        run("run", "--rm", "--no-deps", "--entrypoint", "python", "-T", "sut-management", "-c", shift)
        run("start", "sut-management")
        ready()
        verify = (
            "import sqlite3; c=sqlite3.connect('/app/data/sut.db'); "
            f"assert c.execute('SELECT status FROM reservations WHERE id=?',({booking_id},)).fetchone()[0]=='no_show'; "
            f"assert c.execute('SELECT count(*) FROM current_usages WHERE sut_id=?',({sut},)).fetchone()[0]==0; "
            "assert c.execute(\"SELECT count(*) FROM audit_events WHERE event_type='offer_timeout'\").fetchone()[0]==1; "
            "assert c.execute(\"SELECT count(*) FROM audit_events WHERE event_type='reservation_no_show'\").fetchone()[0]==1; "
            "print('Restart catch-up: one timeout, one no-show, no automatic usage')"
        )
        run("exec", "-T", "sut-management", "python", "-c", verify)
        rows = following.get(f"/api/v1/suts/{sut}/queue").json()["items"]
        assert len(rows) == 1 and rows[0]["offer_status"] == "notified"
        assert (
            mutation(first, "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1}).status_code == 409
        )
        claimed = mutation(following, "POST", f"/api/v1/suts/{sut}/claim", {"duration_minutes": 1})
        assert claimed.status_code == 201, claimed.text
        assert (
            mutation(
                following, "POST", f"/api/v1/suts/{sut}/release", {"usage_key": claimed.json()["usage_key"]}
            ).status_code
            == 200
        )
        assert client.get(f"/api/v1/history?sut_id={sut}").json()["total"] == 2
        # Exercise periodic expiry in the live process, using no HTTP requests until
        # a direct database assertion has proved the background transition occurred.
        now = datetime.now(UTC)
        booking = mutation(
            client,
            "POST",
            "/api/v1/reservations",
            {
                "sut_id": sut,
                "start_time": (now + timedelta(hours=3)).isoformat(),
                "end_time": (now + timedelta(hours=4)).isoformat(),
                "purpose": "Synthetic live deadline",
            },
        ).json()
        live_id = booking["id"]
        shift_live = (
            "import sqlite3; from datetime import datetime,UTC,timedelta; "
            "c=sqlite3.connect('/app/data/sut.db'); n=datetime.now(UTC).replace(tzinfo=None); "
            f"c.execute('UPDATE reservations SET start_time=?,end_time=? WHERE id=?',((n-timedelta(minutes=20)).isoformat(' '),(n+timedelta(hours=2)).isoformat(' '),{live_id})); c.commit()"
        )
        run("exec", "-T", "sut-management", "python", "-c", shift_live)
        time.sleep(2)
        direct = (
            "import sqlite3; c=sqlite3.connect('/app/data/sut.db'); "
            f"assert c.execute('SELECT status FROM reservations WHERE id=?',({live_id},)).fetchone()[0]=='no_show'; "
            "assert c.execute(\"SELECT count(*) FROM notifications WHERE event_key LIKE 'no-show:%'\").fetchone()[0]==2; "
            "print('Live deadline processing without HTTP/browser: OK')"
        )
        run("exec", "-T", "sut-management", "python", "-c", direct)
        before = len(client.get("/api/v1/notifications").json()["items"])
        run("restart", "sut-management")
        ready()
        assert len(client.get("/api/v1/notifications").json()["items"]) == before
        run("exec", "-T", "sut-management", "python", "-c", direct)
        print(
            "PASS: Day 2 Docker Claim/Release/FIFO/history, offline deadline catch-up, live background no-show and restart-idempotent notifications"
        )
