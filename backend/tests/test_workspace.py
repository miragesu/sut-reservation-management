"""Accepted workspace/navigation boundaries, independent of Demo runtime files."""

from conftest import identity, mutate
from coordination_helpers import claim, reserve


def test_my_suts_is_own_only_for_users_and_admins_and_ignores_foreign_scope(arena, application):
    users, sut, sut2, clock = arena
    claim(users["rd"], sut, purpose="RD active only")
    claim(users["root"], sut2, purpose="Admin active only")
    own = reserve(users["rd"], sut, clock, start=120, purpose="RD booking only")
    other = reserve(users["root"], sut2, clock, start=120, purpose="Admin booking only")
    for name, visible, hidden in [
        ("rd", "RD booking only", "Admin booking only"),
        ("root", "Admin booking only", "RD booking only"),
    ]:
        foreign = identity(application, "root" if name == "rd" else "rd")
        text = users[name].get(f"/my-suts?user_id={foreign}").text
        assert visible in text and hidden not in text
        assert ("RD active only" in text) == (name == "rd")
        assert ("Admin active only" in text) == (name == "root")
    assert mutate(users["rd"], "DELETE", f"/api/v1/reservations/{own['id']}").status_code == 200
    mine = users["rd"].get("/my-suts").text
    assert "RD booking only" not in mine and "0 reservations" in mine
    calendar = users["rd"].get("/calendar").text
    assert "RD booking only" in calendar and "Admin booking only" in calendar
    assert (
        users["rd"].get(f"/api/v1/reservations/{other['id']}").status_code == 200
    )  # Shared coordination remains.


def test_navigation_and_legacy_redirects(arena):
    users, _, _, _ = arena
    for name in ("rd", "lab", "root"):
        nav = users[name].get("/").text.split("</nav>", 1)[0]
        assert 'href="/my-suts"' in nav and "My SUTs" in nav
        assert 'href="/labs"' not in nav and 'href="/suts"' not in nav
        assert "🔔" not in nav
        assert ('href="/admin"' in nav) == (name != "rd")
        assert nav.index('href="/profile"') < nav.index('action="/logout"')
        for path in ("/my-usage", "/reservations?user_id=999"):
            response = users[name].get(path, follow_redirects=False)
            assert response.status_code == 303 and response.headers["location"].startswith("/my-suts")
    assert users["rd"].get("/admin").status_code == 403


def test_timeline_named_selector_and_inbox_controls_are_not_global(arena):
    users, _, _, _ = arena
    calendar = users["rd"].get("/calendar").text
    assert 'class="calendar-day-track' in calendar and 'id="calendar-sut" name="sut_id"' in calendar
    assert "<optgroup" in calendar and "calendar.js" in calendar
    assert 'type="number"' not in calendar
    dashboard = users["rd"].get("/").text
    assert 'id="desktop-opt-in"' not in dashboard and "Recent notifications" not in dashboard
    assert 'name="search"' not in dashboard and 'name="platform"' not in dashboard
    assert 'value="name"' in dashboard and 'value="status"' in dashboard
    inbox = users["rd"].get("/notifications").text
    assert 'id="desktop-opt-in"' in inbox and "Enable desktop notifications" in inbox
