from datetime import timedelta
from sqlalchemy import func, select
from app.core.database import unit_of_work
from conftest import mutate


def claim(client, sut, minutes=60, **extra):
    response = mutate(
        client,
        "POST",
        f"/api/v1/suts/{sut}/claim",
        {"duration_minutes": minutes, "purpose": "Synthetic coordination", **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def release(client, sut, usage, *, force=False, reason=""):
    return mutate(
        client,
        "POST",
        f"/api/v1/suts/{sut}/" + ("force-release" if force else "release"),
        {"usage_key": usage["usage_key"], "reason": reason},
    )


def join(client, sut, minutes=60):
    response = mutate(client, "POST", f"/api/v1/suts/{sut}/queue", {"requested_duration_minutes": minutes})
    assert response.status_code == 201, response.text
    return response.json()


def reserve(client, sut, clock, start=60, length=60, **extra):
    data = {
        "sut_id": sut,
        "start_time": (clock.now + timedelta(minutes=start)).isoformat(),
        "end_time": (clock.now + timedelta(minutes=start + length)).isoformat(),
        "purpose": "Synthetic reservation",
        **extra,
    }
    response = mutate(client, "POST", "/api/v1/reservations", data)
    assert response.status_code == 201, response.text
    return response.json()


def count(application, model, *conditions):
    with unit_of_work(application.state.engine) as db:
        return db.scalar(select(func.count()).select_from(model).where(*conditions))
