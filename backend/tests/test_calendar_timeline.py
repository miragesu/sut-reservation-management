import unittest
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.calendar import day_events

TZ = ZoneInfo("Asia/Taipei")
DAY = date(2026, 10, 16)


def booking(identity, start, end):
    return {
        "id": identity,
        "start_time": datetime.fromisoformat(start).replace(tzinfo=TZ),
        "end_time": datetime.fromisoformat(end).replace(tzinfo=TZ),
    }


class CalendarTimelineTests(unittest.TestCase):
    def test_cross_midnight_is_split_and_clipped(self):
        rows = [booking(1, "2026-10-16T23:30", "2026-10-17T00:30")]
        first, second = day_events(rows, DAY)[0], day_events(rows, date(2026, 10, 17))[0]
        self.assertEqual((first["top"], first["height"], first["time_label"]), (1410, 30, "23:30–24:00"))
        self.assertTrue(first["continues_after"])
        self.assertEqual((second["top"], second["height"]), (0, 30))
        self.assertTrue(second["continues_before"])

    def test_overlap_uses_separate_lanes(self):
        rows = [
            booking(1, "2026-10-16T09:00", "2026-10-16T11:00"),
            booking(2, "2026-10-16T10:00", "2026-10-16T12:00"),
            booking(3, "2026-10-16T12:00", "2026-10-16T13:00"),
        ]
        events = day_events(rows, DAY)
        self.assertEqual([(e["lane"], e["lanes"]) for e in events], [(0, 2), (1, 2), (0, 1)])

    def test_midnight_end_is_not_repeated_next_day(self):
        self.assertEqual(day_events([booking(1, "2026-10-15T23:00", "2026-10-16T00:00")], DAY), [])

    def test_short_events_have_readable_geometry_and_no_visual_overlap(self):
        events = day_events(
            [
                booking(1, "2026-10-16T09:00", "2026-10-16T09:05"),
                booking(2, "2026-10-16T09:05", "2026-10-16T09:10"),
            ],
            DAY,
        )
        self.assertEqual(events[0]["height"], 30)
        self.assertNotEqual(events[0]["lane"], events[1]["lane"])

    def test_all_records_visible_without_list_pagination(self):
        events = day_events([booking(i, "2026-10-16T09:00", "2026-10-16T10:00") for i in range(30)], DAY)
        self.assertEqual(len(events), 30)
        self.assertTrue(all(e["lanes"] == 30 for e in events))


if __name__ == "__main__":
    unittest.main()
