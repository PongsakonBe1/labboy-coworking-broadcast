"""ตรวจ diagnosis/recovery ด้วย HTTP จำลอง ไม่เชื่อมต่อ K-Room หรือลำโพงจริง."""
import io
import json
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from unittest.mock import Mock, patch

import requests
import desktop_diagnostics as checks
import web_ui as ui

ROOMS = {'Linux': {'number': '306', 'ip': '192.0.2.1', 'audio_id': 13}}


def response(code=200, body=b'{"AudioAlarmCap":{}}'):
    result = Mock(status_code=code)
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = [body]
    result.history = [Mock(status_code=401)]
    result.request = Mock(headers={'Authorization': 'Digest simulated-test-only'})
    return result


class ProbeTests(unittest.TestCase):
    def session(self, reply=None, error=None):
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        session.get.return_value = reply
        if error:
            session.get.side_effect = error
        return session

    def test_configuration_and_invalid_url(self):
        self.assertEqual(checks.check_configuration('https://example.org/calendar', ROOMS)['kind'], 'green')
        self.assertEqual(checks.check_configuration('https://admin:secret@example.org/calendar', ROOMS)['action'], 'settings')
        self.assertEqual(checks.check_configuration('https://example.org/calendar', {})['kind'], 'red')
        self.assertEqual(checks.check_configuration('https://example.org/calendar', {'X': {'ip': ''}})['kind'], 'red')

    def test_calendar_probe_with_real_local_http_and_changed_markup(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'<html><div id="calendar"></div></html>' if self.path == '/calendar' else b'<html>login</html>')
            def log_message(self, *_):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = 'http://127.0.0.1:' + str(server.server_port)
            ok = checks.probe_calendar(base + '/calendar', threading.Event())
            changed = checks.probe_calendar(base + '/login', threading.Event())
            self.assertEqual([r['kind'] for r in ok], ['green', 'green'])
            self.assertEqual(changed[-1]['key'], 'calendar')
            self.assertEqual(changed[-1]['kind'], 'red')
            self.assertIn('ผู้พัฒนา', changed[-1]['detail'])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1)

    def test_calendar_timeout_has_action_and_does_not_echo_exception_secrets(self):
        session = self.session(error=requests.Timeout('secret-url-token'))
        with patch.object(checks.requests, 'Session', return_value=session):
            result = checks.probe_calendar('https://example.org/calendar', threading.Event())
        self.assertEqual(result[0]['action'], 'retry')
        self.assertNotIn('secret-url-token', json.dumps(result))
        self.assertNotIn('auth', session.get.call_args.kwargs)

    def test_capabilities_is_read_only_and_not_a_sound_confirmation(self):
        session = self.session(response())
        with patch.object(checks.requests, 'Session', return_value=session):
            result = checks.probe_speaker('Linux', ROOMS['Linux'], 'test-secret', threading.Event())
        self.assertEqual(result['kind'], 'green')
        self.assertIn('ไม่เล่นเสียง', result['detail'])
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertIn('/capabilities?format=json', session.get.call_args.args[0])
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])
        session.put.assert_not_called()
        session.post.assert_not_called()

    def test_401_is_password_failure_but_403_is_not_assumed_wrong_password(self):
        for status, expected in [(401, 'password'), (403, 'settings'), (404, 'settings')]:
            with self.subTest(status=status), patch.object(checks.requests, 'Session', return_value=self.session(response(status))):
                result = checks.probe_speaker('Linux', ROOMS['Linux'], 'test-only', threading.Event())
            self.assertEqual(result['action'], expected)

    def test_http_200_with_error_body_is_not_green(self):
        with patch.object(checks.requests, 'Session', return_value=self.session(response(body=b'{"statusCode":4}'))):
            result = checks.probe_speaker('Linux', ROOMS['Linux'], 'test-only', threading.Event())
        self.assertEqual(result['kind'], 'amber')

    def test_public_capabilities_without_auth_cannot_confirm_password(self):
        reply = response()
        reply.history = []
        reply.request.headers = {}
        with patch.object(checks.requests, 'Session', return_value=self.session(reply)):
            result = checks.probe_speaker('Linux', ROOMS['Linux'], 'test-only', threading.Event())
        self.assertEqual(result['kind'], 'blue')
        self.assertIn('ยังยืนยันรหัสผ่านไม่ได้', result['detail'])

    def test_invalid_ip_and_missing_password_do_not_make_requests(self):
        with patch.object(checks.requests, 'Session') as factory:
            self.assertEqual(checks.probe_speaker('Linux', ROOMS['Linux'], '', threading.Event())['action'], 'password')
            self.assertEqual(checks.probe_speaker('Linux', {'ip': ''}, 'test-only', threading.Event())['action'], 'settings')
        factory.assert_not_called()

    def test_cancellation_does_not_start_network_calls(self):
        cancel = threading.Event()
        cancel.set()
        with patch.object(checks.requests, 'Session') as factory:
            self.assertEqual(checks.probe_calendar('https://example.org/', cancel), [])
            checks.probe_speaker('Linux', ROOMS['Linux'], 'test-only', cancel)
        factory.assert_not_called()


class ControllerDiagnosticTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('read_password', 'test-secret'), ('windows_startup_enabled', False),
                            ('_load_previous_logs', None), ('_load_sound_state', None)]:
            item = patch.object(ui.BroadcastController, name, return_value=value)
            item.start()
            self.addCleanup(item.stop)
        item = patch.object(ui, 'load_preferences', return_value={})
        item.start()
        self.addCleanup(item.stop)
        self.c = ui.BroadcastController()
        self.c.rooms = ROOMS
        self.c.schedule_url = 'https://example.org/calendar'
        self.c.process = Mock(poll=Mock(return_value=None), stdout=io.StringIO(''), wait=Mock(return_value=0))
        self.c.is_monitor_session = True

    def test_diagnostic_start_returns_without_io_and_deduplicates(self):
        with patch.object(ui.threading, 'Thread') as thread, patch.object(checks, 'probe_calendar') as web:
            self.assertTrue(self.c.start_diagnostics()['ok'])
            self.assertTrue(self.c.start_diagnostics()['ok'])
        thread.assert_called_once()
        web.assert_not_called()
        self.assertTrue(self.c.get_state()['diagnostics']['running'])
        self.assertNotIn('test-secret', json.dumps(self.c.get_state()))

    def test_worker_preserves_monitor_and_sound_state_and_runs_only_probes(self):
        process = self.c.process
        self.c.records = {'sent': {'alert': 'ส่งเสียงแล้ว'}}
        snapshot = {'url': self.c.schedule_url, 'rooms': ROOMS, 'password': 'test-secret', 'revision': 0}
        with patch.object(checks, 'probe_calendar', return_value=[checks.row('web', 'เว็บ', 'green', 'ผ่าน')]), \
                patch.object(checks, 'probe_speaker', return_value=checks.row('speaker:Linux', 'ลำโพง', 'green', 'ผ่าน')), \
                patch.object(self.c, 'pause_monitor') as pause, patch.object(self.c, 'start_monitor') as start:
            self.c._run_diagnostics(snapshot, threading.Event())
        self.assertIs(self.c.process, process)
        self.assertEqual(self.c.records['sent']['alert'], 'ส่งเสียงแล้ว')
        pause.assert_not_called()
        start.assert_not_called()
        self.assertFalse(self.c.diagnostic_state['running'])
        self.assertTrue(self.c.diagnostic_state['checked_at'])

    def test_changed_settings_mark_results_stale(self):
        snapshot = {'url': self.c.schedule_url, 'rooms': ROOMS, 'password': 'test-secret', 'revision': 0}
        def change(*_):
            self.c._invalidate_diagnostics()
            return []
        with patch.object(checks, 'probe_calendar', side_effect=change), \
                patch.object(checks, 'probe_speaker', return_value=checks.row('s', 'ลำโพง', 'green', 'ผ่าน')):
            self.c._run_diagnostics(snapshot, threading.Event())
        self.assertTrue(self.c.diagnostic_state['stale'])

    def test_read_success_from_an_old_session_is_not_reported_as_current_success(self):
        self.c.last_read = self.c.started_at = datetime.now()
        snapshot = {'url': self.c.schedule_url, 'rooms': {}, 'password': '', 'revision': 0}
        self.c._run_diagnostics(snapshot, threading.Event())
        current = next(r for r in self.c.diagnostic_state['rows'] if r['key'] == 'monitor')
        self.assertEqual(current['kind'], 'blue')
        self.assertIn('รอบแรก', current['detail'])
        self.c.read_count = 1
        self.c.diagnostic_state['rows'] = []
        self.c._run_diagnostics(snapshot, threading.Event())
        self.assertEqual(next(r for r in self.c.diagnostic_state['rows'] if r['key'] == 'monitor')['kind'], 'green')

    def test_repeat_scan_is_rate_limited_and_close_rejects_scan(self):
        with patch.object(ui.threading, 'Thread'):
            self.c.start_diagnostics()
            self.c.diagnostic_state['running'] = False
            self.assertFalse(self.c.start_diagnostics()['ok'])
            self.c.shutting_down = True
            self.assertFalse(self.c.start_diagnostics()['ok'])

    def test_saved_password_not_used_by_current_monitor_has_restart_guidance(self):
        with patch.object(ui, 'save_speaker_password'):
            self.c.save_password('changed-test-only', restart=False)
        self.assertTrue(self.c._credentials_pending)
        snapshot = {'url': self.c.schedule_url, 'rooms': {}, 'password': '', 'revision': self.c._diagnostic_revision}
        self.c._run_diagnostics(snapshot, threading.Event())
        monitor = next(r for r in self.c.diagnostic_state['rows'] if r['key'] == 'monitor')
        self.assertEqual(monitor['action'], 'restart')
        self.assertIn('ยังใช้รหัสเดิม', monitor['detail'])

    def test_saved_url_not_used_by_current_monitor_has_restart_guidance(self):
        with patch.object(ui, 'CONFIG_DIR'), patch.object(ui, 'PREFERENCES_FILE'), \
                patch.object(self.c, '_write_startup_registration'):
            result = self.c.save_settings({'schedule_url': 'https://example.org/new-calendar'})
        self.assertTrue(result['ok'])
        self.assertTrue(self.c._settings_pending)
        snapshot = {'url': self.c.schedule_url, 'rooms': {}, 'password': '', 'revision': self.c._diagnostic_revision}
        self.c._run_diagnostics(snapshot, threading.Event())
        monitor = next(r for r in self.c.diagnostic_state['rows'] if r['key'] == 'monitor')
        self.assertEqual(monitor['action'], 'restart')
        self.assertIn('ยังใช้ค่าเดิม', monitor['detail'])

    def test_closing_cancels_diagnostic_without_waiting_for_network(self):
        started = threading.Event()
        def waiting_probe(_url, cancel):
            started.set()
            cancel.wait(timeout=2)
            return []
        with patch.object(checks, 'probe_calendar', side_effect=waiting_probe), \
                patch.object(checks, 'probe_speaker') as speaker, \
                patch.object(self.c, '_terminate_tree', return_value=True), \
                patch.object(self.c, '_stop_awake_thread'):
            self.c.start_diagnostics()
            self.assertTrue(started.wait(timeout=2))
            self.c._shutdown()
            self.c._diagnostic_thread.join(timeout=2)
        self.assertFalse(self.c._diagnostic_thread.is_alive())
        self.assertFalse(self.c.diagnostic_state['running'])
        speaker.assert_not_called()

    def test_confirmed_restart_preserves_mode_and_manual_stop_cancels_restart(self):
        self.c.monitor_mode = 'ทดลอง'
        with patch.object(ui.threading, 'Thread'), patch.object(self.c, 'start_monitor') as start:
            self.c.restart_monitor()
            self.assertTrue(self.c.pending_restart)
            self.c.pause_monitor()
            self.assertFalse(self.c.pending_restart)
            self.c._read_output(self.c.process)
        start.assert_not_called()
        self.assertEqual(self.c.monitor_mode, 'ทดลอง')

    def test_restart_after_reader_exit_does_not_switch_mode(self):
        self.c.monitor_mode = 'ทดลอง'
        with patch.object(ui.threading, 'Thread'), patch.object(self.c, 'start_monitor') as start:
            self.c.restart_monitor()
            self.c._read_output(self.c.process)
        start.assert_called_once_with(automatic=True)
        self.assertEqual(self.c.monitor_mode, 'ทดลอง')


if __name__ == '__main__':
    unittest.main()
