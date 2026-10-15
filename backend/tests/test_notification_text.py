import unittest
from app.services.notification_text import chinese_message


class NotificationTextTests(unittest.TestCase):
    def test_retained_schedule_message_keeps_time_and_equipment(self):
        result = chinese_message(
            "Demo-SUT-2: upcoming reservation scheduled for 2026-10-16 14:00 Asia/Taipei. Manually check in or Claim when it starts."
        )
        self.assertIn("Demo-SUT-2", result)
        self.assertIn("2026-10-16 14:00", result)
        self.assertIn("已安排預約", result)
        self.assertNotIn("Asia/Taipei", result)

    def test_offer_deadline_and_manual_claim_are_preserved(self):
        result = chinese_message(
            "Demo-SUT-5: it is your turn. Manually Claim within 15 minutes; notification is not usage."
        )
        self.assertIn("15 分鐘", result)
        self.assertIn("手動 Start using", result)
        self.assertIn("不代表已開始使用", result)

    def test_translation_is_idempotent(self):
        result = chinese_message("Demo-SUT-1: usage was recorded as released.")
        self.assertEqual(chinese_message(result), result)
        self.assertIn("已記錄使用結束", result)

    def test_maintenance_notice_preserves_retention_message(self):
        result = chinese_message(
            "Demo-SUT-5: operational state changed to maintenance. Existing activity is retained."
        )
        self.assertIn("維護中", result)
        self.assertIn("均保留", result)


if __name__ == "__main__":
    unittest.main()
