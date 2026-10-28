"""ชุดตรวจเบื้องต้นแบบกดรันได้ เก็บรายงาน local โดยไม่สั่งลำโพงจริง."""
from datetime import datetime
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    output = ROOT / 'build' / 'basic-checks'
    output.mkdir(parents=True, exist_ok=True)
    report = output / (datetime.now().strftime('%Y%m%d-%H%M%S') + '.txt')
    steps = [
        ('Controller, monitor rules, GUI and updater', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'], 120),
        ('Contrast in all themes', [sys.executable, 'check_contrast.py'], 30),
        ('Native shutdown / cancel / tray / child process cleanup', [sys.executable, 'tests/smoke_shutdown.py'], 180),
    ]
    node = shutil.which('node')
    if node:
        steps.insert(1, ('Booking filters and sorting', [node, 'tests/test_booking_model.js'], 30))
    if (ROOT / 'build/release/room_speaker_monitor.exe').is_file():
        steps.append(('Monitor EXE UTF-8 pipe (invalid URL; no audio)', [sys.executable, 'tests/smoke_monitor_exe.py'], 40))
    failures = []
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    print('SAFE CHECKS: no real speaker commands, credentials or startup changes.', flush=True)
    print('Temporary test windows may appear. Your running app is not stopped.', flush=True)
    with report.open('w', encoding='utf-8') as log:
        log.write('LabBoy safe basic checks\n')
        if not node:
            log.write('SKIP: JavaScript unit tests (Node.js is not installed)\n')
        for title, command, timeout in steps:
            print('Checking: ' + title, flush=True)
            log.write('\n=== ' + title + ' ===\n')
            log.flush()
            try:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                        stderr=subprocess.STDOUT, timeout=timeout,
                                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                ok = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.write(str(exc) + '\n')
                ok = False
            print(('PASS: ' if ok else 'FAIL: ') + title, flush=True)
            if not ok:
                failures.append(title)
        summary = 'RESULT: ' + ('FAILED' if failures else 'PASSED')
        log.write('\n' + summary + '\n')
    print(summary)
    if not node:
        print('SKIP: JavaScript unit tests; Node.js is not installed.')
    print('Report: ' + str(report))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
