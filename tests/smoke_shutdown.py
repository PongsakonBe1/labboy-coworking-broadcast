"""ทดสอบ WebView2 จริงกับ process พ่อ/ลูกจำลอง ไม่แตะ monitor ที่ใช้งานจริง.

เรียก python tests/smoke_shutdown.py; แต่ละกรณีมี timeout และล้างเฉพาะ process
ที่ชุดทดสอบสร้างขึ้น ไม่อ่านรหัส ไม่เขียน startup ไม่เปิด K-Room/ลำโพง.
"""
import argparse
import ctypes
from ctypes import wintypes
import faulthandler
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SCENARIOS = ('titlebar', 'tray', 'confirm', 'idle', 'cancel', 'hide-tray')


def alive(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 258
    finally:
        kernel.CloseHandle(handle)


def worker(scenario, folder):
    import web_ui as ui
    faulthandler.dump_traceback_later(12)
    marker = Path(folder) / 'fixture.json'
    fixture = None
    if scenario != 'idle':
        script = ("import subprocess,sys,time,json;from pathlib import Path;"
                  "child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(90)']);"
                  "Path(sys.argv[1]).write_text(json.dumps({'parent':__import__('os').getpid(),'child':child.pid}));"
                  "print('SIMULATED MONITOR READY',flush=True);time.sleep(90)")
        fixture = subprocess.Popen([sys.executable, '-u', '-c', script, str(marker)],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                   text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 5
        while not marker.is_file() and time.monotonic() < deadline:
            time.sleep(.02)
        assert marker.is_file(), 'fixture did not start'
    with patch.object(ui.BroadcastController, 'read_password', return_value=''), \
            patch.object(ui.BroadcastController, 'windows_startup_enabled', return_value=False), \
            patch.object(ui.BroadcastController, '_load_previous_logs'), \
            patch.object(ui.BroadcastController, '_load_sound_state'), \
            patch.object(ui.BroadcastController, '_write_startup_registration'), \
            patch.object(ui.BroadcastController, 'start_diagnostics', return_value={'ok': True}), \
            patch.object(ui.BroadcastController, 'save_settings', side_effect=AssertionError('settings writes forbidden')), \
            patch.object(ui.BroadcastController, '_launch_test_process', side_effect=AssertionError('audio forbidden')), \
            patch.object(ui, 'save_speaker_password', side_effect=AssertionError('credential writes forbidden')), \
            patch.object(ui, 'load_preferences', return_value={}), \
            patch.object(ui.BroadcastController, 'start_monitor', side_effect=AssertionError('real monitor forbidden')):
        c = ui.BroadcastController()
        c.rooms = {'Linux': {'number': '306', 'ip': '192.0.2.1', 'audio_id': 13}}
        c.room_results = {'Linux': {'status': 'ข้อมูลจำลอง', 'kind': 'neutral'}}
        c.initialized = True
        c.close_to_tray = scenario == 'hide-tray'
        c.monitor_mode = 'ทดลอง'
        c.process = fixture
        c.is_monitor_session = fixture is not None
        test_tray = None
        if scenario == 'hide-tray':
            test_tray = ui.pystray.Icon('labboy-shutdown-test-' + str(os.getpid()),
                                       ui.Image.new('RGBA', (32, 32), '#0055B8'),
                                       'LabBoy isolated shutdown test')
            c.tray_icon = test_tray
            test_tray.run_detached()
        if fixture:
            c.reader_thread = threading.Thread(target=c._read_output, args=(fixture,), daemon=True)
            c.reader_thread.start()
        window = ui.webview.create_window('LabBoy · isolated shutdown test', str(ui.WEB_DIR / 'index.html'),
                                         js_api=ui.DesktopAPI(c), width=960, height=640,
                                         confirm_close=False)
        c.window = window
        window.events.closing += lambda *_: c._on_closing()
        exercised = threading.Event()

        def loaded(*_):
            if exercised.is_set():
                return
            exercised.set()
            deadline = time.monotonic() + 6
            while not window.evaluate_js("Boolean(window.pywebview?.api?.confirm_exit && typeof window.showCloseConfirm === 'function')"):
                assert time.monotonic() < deadline, 'bridge did not become ready'
                time.sleep(.05)
            # รอ bridge; timer ตอบ dialog จากใน renderer เพื่อจับ UI-thread deadlock.
            window.evaluate_js('''let cancelled=false; setInterval(() => {
                const d=document.getElementById('confirmDialog');
                if(d?.open) {
                    if(''' + json.dumps(scenario == 'cancel') + ''' && !cancelled){
                        cancelled=true; d.querySelector('button[value="cancel"]').click();
                    } else { document.getElementById('confirmButton').click(); }
                }
            },100); undefined;''')
            time.sleep(.1)
            if scenario == 'tray':
                c.request_exit_from_tray()
            elif scenario == 'confirm':
                window.evaluate_js('window.showCloseConfirm(); undefined;')
            else:
                window.destroy()
                if scenario == 'cancel':
                    deadline = time.monotonic() + 4
                    while c.pending_close and time.monotonic() < deadline:
                        time.sleep(.03)
                    time.sleep(.2)
                    assert not c.shutting_down and fixture.poll() is None, 'cancel stopped the monitor'
                    window.destroy()
                elif scenario == 'hide-tray':
                    time.sleep(.3)
                    assert fixture.poll() is None, 'hide-to-tray stopped the monitor'
                    c.request_exit_from_tray()

        window.events.loaded += loaded
        try:
            ui.webview.start(gui='edgechromium', debug=False, http_server=True)
        finally:
            c._shutdown()
    faulthandler.cancel_dump_traceback_later()
    if test_tray:
        assert not test_tray._running, 'test tray icon did not stop'
    if fixture:
        fixture.wait(timeout=3)
        pids = json.loads(marker.read_text())
        assert not alive(pids['child']), 'simulated monitor descendant remained alive'
    print(json.dumps({'scenario': scenario, 'ok': True}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', choices=SCENARIOS)
    parser.add_argument('--folder')
    parser.add_argument('--scenario', choices=SCENARIOS)
    parser.add_argument('--without-system-tray', action='store_true', help='CI without Explorer notification area')
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.folder)
        return
    failures = []
    cases = [args.scenario] if args.scenario else [s for s in SCENARIOS if not (args.without_system_tray and s == 'hide-tray')]
    for scenario in cases:
        with tempfile.TemporaryDirectory(prefix='labboy-shutdown-test-') as folder:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', scenario, '--folder', folder]
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                output, _ = process.communicate(timeout=22)
                passed = process.returncode == 0
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                               capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
                output, _ = process.communicate(timeout=5)
                passed = False
                output += '\nFAIL: native window did not close within 22 seconds'
            finally:
                marker = Path(folder) / 'fixture.json'
                if marker.is_file():
                    for pid in json.loads(marker.read_text()).values():
                        if alive(pid):
                            subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'], capture_output=True,
                                           timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
            print(('PASS' if passed else 'FAIL') + ': ' + scenario, flush=True)
            if not passed:
                print(output[-18000:], flush=True)
                failures.append(scenario)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
