"""ทดสอบด้วย process/credential จำลอง ไม่มีการเชื่อมต่อ K-Room หรือลำโพง."""
import io
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import web_ui as ui


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch.object(ui, "load_preferences", return_value={}),
            patch.object(ui.BroadcastController, "read_password", return_value="test-only"),
            patch.object(ui.BroadcastController, "windows_startup_enabled", return_value=False),
            patch.object(ui.BroadcastController, "_load_previous_logs"),
            patch.object(ui.BroadcastController, "_load_sound_state"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.c = ui.BroadcastController()
        self.c.is_monitor_session = True
        self.c.process = Mock(poll=Mock(return_value=None))
        self.today = datetime.now().strftime("%Y-%m-%d")

    def booking(self, start="13:00", end="16:00", status="กำลังใช้ห้อง", room="Linux"):
        self.c._handle_log(f"{self.today} 15:59:59 INFO พบรายการ: ห้อง {room} | "
                           f"{self.today} {start}–{self.today} {end} | สถานะ={status} สี=#00a65a")
        return f"{room}|{self.today} {start}|{self.today} {end}"

    def summary(self, counts="Linux=1"):
        self.c._handle_log(f"{self.today} 15:59:58 INFO สรุปรายการที่อ่านได้: {counts}")

    def test_result_attaches_to_processed_booking_not_future_booking(self):
        self.summary("Linux=2")
        due = self.booking()
        self.c._handle_log(f"{self.today} 16:00:01 INFO ถึงเวลาสิ้นสุดห้อง Linux เวลา 16:00 กำลังสั่งลำโพง")
        self.c._handle_log(f"{self.today} 16:00:02 INFO สั่งเล่นเสียงห้อง Linux (192.0.2.1) สำเร็จ: HTTP 200")
        future = self.booking("16:00", "19:00", "จองแล้ว")
        self.assertEqual(self.c.records[due]["alert"], "ส่งเสียงแล้ว")
        self.assertNotEqual(self.c.records[future]["alert"], "ส่งเสียงแล้ว")

    def test_manual_test_does_not_mark_a_booking_sent(self):
        key = self.booking()
        self.c.is_monitor_session = False
        self.c._handle_log(f"{self.today} 16:00:02 INFO สั่งเล่นเสียงห้อง Linux (192.0.2.1) สำเร็จ: HTTP 200")
        self.assertNotEqual(self.c.records[key]["alert"], "ส่งเสียงแล้ว")
        self.assertEqual(self.c.successes, 0)

    def test_successful_test_updates_sidebar_without_a_parseable_log(self):
        process = Mock(stdout=io.StringIO(''), wait=Mock(return_value=0))
        self.c.process = process
        self.c.is_monitor_session = False
        self.c._read_test_output(process, resume=False, room='Linux', confirmed=True)
        result = next(room for room in self.c.get_state()['room_cards'] if room['name'] == 'Linux')
        self.assertEqual(result['status_kind'], 'green')
        self.assertIn('ทดสอบเสียงสำเร็จ', result['status'])
        self.assertEqual(self.c.status_kind, result['status_kind'])
        self.assertEqual(self.c.room_results['Windows']['status'], 'ยังไม่มีผลทดสอบ')

    def test_failed_test_updates_sidebar_without_a_parseable_log(self):
        process = Mock(stdout=io.StringIO(''), wait=Mock(return_value=1))
        self.c.process = process
        self.c.is_monitor_session = False
        self.c._read_test_output(process, resume=False, room='Windows', confirmed=True)
        self.assertEqual(self.c.room_results['Windows']['kind'], 'red')
        self.assertIn('ไม่สำเร็จ', self.c.room_results['Windows']['status'])

    def test_zero_exit_without_play_confirmation_is_not_success(self):
        process = Mock(stdout=io.StringIO(''), wait=Mock(return_value=0))
        self.c.process = process
        self.c.is_monitor_session = False
        self.c._read_test_output(process, resume=False, room='Linux', confirmed=False)
        self.assertNotEqual(self.c.room_results['Linux']['kind'], 'green')
        self.assertNotEqual(self.c.status_kind, 'green')

    def test_new_snapshot_removes_cancelled_bookings(self):
        self.summary("Linux=2")
        old = self.booking()
        self.booking("16:00", "19:00")
        self.summary()
        kept = self.booking("16:00", "19:00")
        self.assertNotIn(old, self.c.records)
        self.assertIn(kept, self.c.records)
        self.summary("Linux=0")
        self.assertFalse(self.c.records)

    def test_counts_support_new_rooms(self):
        self.summary("Windows=1, Design Lab=3")
        self.assertEqual(self.c.booking_count, 4)

    def test_pending_banner_survives_status_change_and_ignores_old_bookings(self):
        now = datetime.now()
        key = self.booking()
        row = self.c.records[key]
        row["end_dt"] = now - timedelta(seconds=5)
        row["status"] = "หมดเวลา"
        self.assertIsNotNone(self.c._next_broadcast(now))
        row["end_dt"] = now - timedelta(minutes=10)
        self.assertIsNone(self.c._next_broadcast(now))

    def test_paused_system_has_no_next_broadcast(self):
        self.booking()
        self.c.process = None
        self.assertIsNone(self.c._next_broadcast(datetime.now()))

    def test_state_is_json_serializable_and_does_not_contain_password(self):
        self.booking()
        value = json.dumps(self.c.get_state(), ensure_ascii=False)
        self.assertNotIn("test-only", value)

    def test_crash_status_is_not_overwritten_by_polling(self):
        self.c.process = None
        self.c.started_at = datetime.now()
        self.c.status = "ระบบหยุดด้วยข้อผิดพลาด (3)"
        self.c.status_kind = "red"
        self.assertEqual(self.c.get_state()["status_kind"], "red")

    def test_password_change_reports_deferred_use(self):
        with patch.object(ui, "save_speaker_password"):
            result = self.c.save_password("new-test-only")
        self.assertTrue(result["ok"])
        self.assertIn("ครั้งถัดไป", result["message"])

    def test_shutdown_cancels_queued_test_and_resume(self):
        self.c.pending_test_room = "Linux"
        self.c.resume_after_test = True
        with patch.object(self.c, "_terminate_tree"), patch.object(self.c, "_stop_awake_thread"):
            self.c._shutdown()
        self.assertIsNone(self.c.pending_test_room)
        self.assertFalse(self.c.resume_after_test)
        self.assertFalse(self.c.start_monitor()["ok"])

    def test_test_completion_resumes_previous_mode(self):
        self.c.monitor_mode = "ทดลอง"
        self.c.resume_after_test = True
        process = Mock(stdout=io.StringIO(""), wait=Mock(return_value=0))
        self.c.process = process
        with patch.object(self.c, "start_monitor") as start:
            self.c._read_test_output(process, resume=True)
        start.assert_called_once_with(automatic=True)
        self.assertEqual(self.c.monitor_mode, "ทดลอง")

    def test_explicit_pause_during_test_does_not_restart_monitor(self):
        process = Mock(stdout=io.StringIO(""), wait=Mock(return_value=1), poll=Mock(return_value=None))
        self.c.process = process
        self.c.is_monitor_session = False
        self.c.resume_after_test = True
        with patch.object(ui.threading, "Thread"), patch.object(self.c, "start_monitor") as start:
            self.c.pause_monitor()
            self.c._read_test_output(process, resume=True)
        start.assert_not_called()

    def test_bridge_does_not_expose_credential_reader(self):
        bridge = ui.DesktopAPI(self.c)
        self.assertFalse(hasattr(bridge, "read_password"))
        self.assertFalse(hasattr(bridge, "password"))

    def test_heartbeat_is_coalesced(self):
        for _ in range(20):
            self.c._append_activity("", title="ตรวจตารางเรียบร้อย", subtitle="พบรายการจอง 2 รายการ")
        self.assertEqual(len(self.c.activities), 1)

    def test_persisted_state_restores_sent_outcome(self):
        signature = f'{self.today}|Linux|{self.today}T13:00:00+07:00|{self.today}T16:00:00+07:00'
        state_file = Mock(read_text=Mock(return_value=json.dumps({
            'triggered':[signature], 'observed_in_use':[signature]})))
        # ใช้ implementation เดิมโดยตรง เพราะ setUp ปิดการอ่านไฟล์จริงไว้.
        self.patches[4].stop()
        with patch.object(ui, 'STATE_FILE', state_file):
            self.c._load_sound_state()
        key = self.booking(status='หมดเวลา')
        self.assertEqual(self.c.records[key]['alert'], 'ส่งเสียงแล้ว')
        self.assertTrue(self.c.records[key]['observed_in_use'])


if __name__ == "__main__":
    unittest.main()
