"""ทดสอบกฎประกาศของ monitor เดิม โดยจำลอง browser และ trigger_speaker ทั้งหมด."""
import logging
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

with patch('logging.basicConfig'), patch('logging.handlers.RotatingFileHandler', return_value=logging.NullHandler()):
    import room_speaker_monitor as monitor


class MonitorContractTests(unittest.TestCase):
    def poll(self, status, observed=False, live=True, age=1, triggered=False):
        now = datetime.now(monitor.LOCAL_TZ)
        row = {'room':'Linux', 'start':now-timedelta(hours=1),
               'end':now-timedelta(seconds=age), 'status':status,
               'color':'#00a65a', 'signature':'test-booking'}
        page = Mock()
        page.expect_response.return_value.__enter__ = Mock(return_value=Mock(value=Mock(ok=True)))
        page.expect_response.return_value.__exit__ = Mock(return_value=False)
        sent = {'test-booking'} if triggered else set()
        seen = {'test-booking'} if observed else set()
        with patch.object(monitor, 'read_bookings', return_value=[row]), \
                patch.object(monitor, 'trigger_speaker', return_value=True) as speaker, \
                patch.object(monitor, 'save_trigger_state'), patch.object(monitor, 'log'):
            monitor.poll_once(page, sent, seen, live)
        return speaker, sent

    def test_expired_booking_with_observed_usage_is_announced_once(self):
        speaker, sent = self.poll('หมดเวลา', observed=True)
        speaker.assert_called_once_with('Linux')
        self.assertIn('test-booking', sent)
        speaker, _ = self.poll('หมดเวลา', observed=True, triggered=True)
        speaker.assert_not_called()

    def test_no_checkin_suspended_unknown_and_stale_do_not_announce(self):
        for status, observed, age in [('หมดเวลา',False,1),('ระงับการจอง',True,1),
                                       ('ไม่ทราบสถานะ',True,1),('หมดเวลา',True,120)]:
            with self.subTest(status=status, observed=observed, age=age):
                speaker, _ = self.poll(status,observed,age=age)
                speaker.assert_not_called()

    def test_dry_run_never_triggers_audio(self):
        speaker, sent = self.poll('หมดเวลา', observed=True, live=False)
        speaker.assert_not_called()
        self.assertFalse(sent)

    def test_future_booking_is_not_announced(self):
        speaker, _ = self.poll('กำลังใช้ห้อง', age=-60)
        speaker.assert_not_called()


if __name__ == '__main__':
    unittest.main()
