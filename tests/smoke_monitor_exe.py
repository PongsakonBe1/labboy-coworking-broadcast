"""ตรวจ encoding ของ EXE จริงในโฟลเดอร์แยก ไม่เปิดเว็บ/อ่านรหัส/สั่งเสียง.

ใช้ URL ที่ไม่ผ่าน validation เพื่อจบก่อน single-instance lock และ browser.
รันหลัง build: python tests/smoke_monitor_exe.py
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile


def main():
    source = Path(__file__).resolve().parents[1] / 'build' / 'release' / 'room_speaker_monitor.exe'
    if not source.is_file():
        raise SystemExit('Build room_speaker_monitor.exe before this smoke test')
    with tempfile.TemporaryDirectory(prefix='labboy-stdio-smoke-') as folder:
        root = Path(folder)
        executable = root / source.name
        shutil.copy2(source, executable)
        env = os.environ.copy()
        env['SCHEDULE_URL'] = 'invalid-smoke-test-url'
        # Frozen interpreter ต้องพึ่ง runtime hook ไม่พึ่งค่า Python env ของผู้ใช้.
        for name in ('SPEAKER_PASSWORD', 'PYTHONIOENCODING', 'PYTHONUTF8'):
            env.pop(name, None)
        result = subprocess.run([str(executable)], cwd=root, env=env,
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 2, f'Unexpected validation exit: {result.returncode}'
        text = result.stdout.decode('utf-8', errors='strict')
        assert 'SCHEDULE_URL ไม่ใช่ URL ที่ถูกต้อง' in text, ascii(text)
        assert '\ufffd' not in text, ascii(text)
        assert 'Logging error' not in text, ascii(text)
        print('PASS: real monitor EXE emits Thai UTF-8 through GUI-style pipe; no web/audio commands')


if __name__ == '__main__':
    main()
