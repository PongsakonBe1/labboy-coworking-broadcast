"""ตรวจ transport ของ log ภาษาไทยโดยไม่เปิด browser หรือสั่งลำโพง."""
import io
import logging
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch


HOOK = Path(__file__).resolve().parents[1] / 'pyinstaller_hooks' / 'monitor_utf8_stdio.py'


class MonitorStdioTests(unittest.TestCase):
    def test_thai_booking_and_en_dash_survive_legacy_windows_codepages(self):
        message = ('พบรายการ: ห้อง Linux | 2026-10-28 13:00–2026-10-28 16:00 '
                   '| สถานะ=กำลังใช้ห้อง สี=#00a65a')
        for encoding in ('cp874', 'cp1252'):
            with self.subTest(encoding=encoding):
                streams = {name: io.TextIOWrapper(io.BytesIO(), encoding=encoding)
                           for name in ('stdin', 'stdout', 'stderr')}
                try:
                    with patch.multiple(sys, **streams):
                        runpy.run_path(str(HOOK))
                        handler = logging.StreamHandler()
                        handler.setFormatter(logging.Formatter('%(levelname)s %(message)s'))
                        handler.handle(logging.LogRecord('test', logging.INFO, '', 0, message, (), None))
                        wire = streams['stderr'].buffer.getvalue()
                        sys.stdout.write(message + '\n')
                        self.assertEqual(sys.stdout.buffer.getvalue().decode('utf-8').strip(), message)
                        self.assertTrue(all(stream.encoding == 'utf-8' for stream in streams.values()))
                    self.assertEqual(wire.decode('utf-8').strip(), 'INFO ' + message)
                finally:
                    for stream in streams.values():
                        stream.close()

    def test_missing_or_replaced_streams_do_not_crash_hook(self):
        with patch.multiple(sys, stdin=None, stdout=io.StringIO(), stderr=io.StringIO()):
            runpy.run_path(str(HOOK))


if __name__ == '__main__':
    unittest.main()
