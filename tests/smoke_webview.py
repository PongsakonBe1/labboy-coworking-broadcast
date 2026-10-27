"""เปิด WebView จริงชั่วคราวโดยปิด credential/startup/monitor ทั้งหมด แล้วตรวจ bridge.

ใช้ด้วย Python บน Windows เท่านั้น: py -3 tests/smoke_webview.py
"""
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_ui as ui


def main():
    controllers, results = [], []
    original_init, original_start = ui.BroadcastController.__init__, ui.webview.start

    def record_init(self):
        original_init(self)
        controllers.append(self)

    def checked_start(func=None, **kwargs):
        window = ui.webview.windows[-1]

        def finish(value):
            results.append(value)
            controllers[0].close_accepted = True
            window.destroy()

        def loaded(*_):
            window.evaluate_js('''new Promise(resolve => {
                let attempts = 0;
                const timer = setInterval(() => {
                    if(window.pywebview?.api?.get_state) {
                        clearInterval(timer);
                        window.pywebview.api.get_state().then(state => resolve({
                            ok: !state.running && !state.settings.has_password,
                            credentialReaderExposed: typeof window.pywebview.api.read_password !== 'undefined',
                            heading: document.querySelector('h1').textContent,
                            font: getComputedStyle(document.querySelector('h1')).fontFamily
                        }));
                    } else if (++attempts > 120) {
                        clearInterval(timer); resolve({ok:false,error:'bridge timeout'});
                    }
                }, 25);
            })''', callback=finish)

        window.events.loaded += loaded
        timeout = threading.Timer(20, lambda: finish({'ok':False,'error':'window timeout'}))
        timeout.start()
        try:
            return original_start(func, **kwargs)
        finally:
            timeout.cancel()

    # ไม่อ่านรหัสจริง ไม่เขียน Run registry และไม่อนุญาตให้สร้าง monitor process.
    with patch.object(ui.BroadcastController, '__init__', record_init), \
            patch.object(ui.BroadcastController, 'read_password', return_value=''), \
            patch.object(ui.BroadcastController, 'windows_startup_enabled', return_value=False), \
            patch.object(ui, 'load_preferences', return_value={}), \
            patch.object(ui.BroadcastController, '_write_startup_registration'), \
            patch.object(ui.BroadcastController, '_load_previous_logs'), \
            patch.object(ui.BroadcastController, '_load_sound_state'), \
            patch.object(ui.BroadcastController, 'start_monitor', side_effect=AssertionError('real monitor forbidden')), \
            patch.object(ui.webview, 'start', checked_start):
        ui.run()
    print(json.dumps(results, ensure_ascii=False))
    if not results or not results[0].get('ok') or results[0].get('credentialReaderExposed'):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
