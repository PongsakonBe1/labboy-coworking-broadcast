"""Regression ของ close lifecycle; ไม่สร้าง monitor หรือแก้ Windows จริง."""
import io
import unittest
from unittest.mock import Mock, patch

import web_ui as ui


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('read_password', ''), ('windows_startup_enabled', False),
                            ('_load_previous_logs', None), ('_load_sound_state', None)]:
            item = patch.object(ui.BroadcastController, name, return_value=value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(ui, 'load_preferences', return_value={})
        item.start()
        self.addCleanup(item.stop)
        self.c = ui.BroadcastController()
        self.c.window = Mock()
        self.c.process = Mock(pid=12345, poll=Mock(return_value=None))

    def test_closing_event_defers_webview_calls_and_deduplicates_prompt(self):
        with patch.object(ui.threading, 'Thread') as thread:
            self.assertFalse(self.c._on_closing())
            self.assertFalse(self.c._on_closing())
            self.c.window.evaluate_js.assert_not_called()
            thread.assert_called_once()
            thread.call_args.kwargs['target']()
        self.c.window.evaluate_js.assert_called_once_with('window.showCloseConfirm(); undefined;')

    def test_cancel_allows_a_new_close_prompt(self):
        with patch.object(ui.threading, 'Thread') as thread:
            self.c._on_closing()
            self.c.cancel_exit()
            self.c._on_closing()
        self.assertEqual(thread.call_count, 2)

    def test_confirm_returns_before_cleanup_and_only_one_worker_starts(self):
        with patch.object(ui.threading, 'Thread') as thread, patch.object(self.c, '_shutdown', return_value=True) as stop:
            result = self.c.confirm_exit()
            self.c.confirm_exit()
            self.assertTrue(result['closing'])
            self.assertFalse(self.c.close_accepted)
            stop.assert_not_called()
            self.c.window.destroy.assert_not_called()
            thread.assert_called_once()
            thread.call_args.kwargs['target']()
        stop.assert_called_once()
        self.c.window.destroy.assert_called_once()
        self.assertTrue(self.c._on_closing())

    def test_shutdown_is_idempotent_and_cancels_pending_actions(self):
        self.c.process = None
        self.c.pending_test_room = 'Linux'
        self.c.resume_after_test = self.c.pending_restart = True
        tray = self.c.tray_icon = Mock()
        with patch.object(self.c, '_stop_awake_thread') as awake:
            self.assertTrue(self.c._shutdown())
            self.assertTrue(self.c._shutdown())
        tray.stop.assert_called_once()
        awake.assert_called_once()
        self.assertIsNone(self.c.pending_test_room)
        self.assertFalse(self.c.resume_after_test or self.c.pending_restart)

    def test_failed_termination_keeps_window_open_with_retry_message(self):
        with patch.object(self.c, '_terminate_tree', return_value=False):
            self.c._finish_exit()
        self.c.window.destroy.assert_not_called()
        self.assertFalse(self.c.shutting_down)
        self.assertEqual(self.c.get_state()['status_kind'], 'red')
        self.assertIn('ลองปิดอีกครั้ง', self.c.status)

    def test_process_tree_exit_is_waited_for(self):
        with patch.object(ui.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertTrue(self.c._terminate_tree(self.c.process))
        self.assertEqual(run.call_args.args[0], ['taskkill.exe', '/PID', '12345', '/T', '/F'])
        self.c.process.wait.assert_called_once_with(timeout=3)

    def test_tree_kill_failure_does_not_kill_only_parent_and_hide_failure(self):
        with patch.object(ui.subprocess, 'run', return_value=Mock(returncode=1)):
            self.assertFalse(self.c._terminate_tree(self.c.process))
        self.c.process.kill.assert_not_called()

    def test_bridge_refuses_new_actions_while_exiting(self):
        self.c.shutting_down = True
        self.assertFalse(ui.DesktopAPI(self.c).pause_monitor()['ok'])
        self.assertTrue(ui.DesktopAPI(self.c).get_state()['closing'])

    def test_old_reader_cannot_clear_a_new_monitor(self):
        old = Mock(stdout=io.StringIO(''), wait=Mock(return_value=0))
        active = self.c.process
        self.c.is_monitor_session = True
        self.c._read_output(old)
        self.assertIs(self.c.process, active)
        self.assertTrue(self.c.is_monitor_session)


if __name__ == '__main__':
    unittest.main()
