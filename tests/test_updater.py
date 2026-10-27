"""ตรวจตัวอัปเดตด้วย executable จำลอง ไม่หยุด process จริงและไม่เปิดแอปจริง."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'update_app.ps1'
NAMES = ('room_speaker_monitor.exe', 'labboy_coworking_broadcast.exe')


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell updater')
class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='labboy-updater-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        release = self.root / 'build' / 'release'
        release.mkdir(parents=True)
        for name in NAMES:
            (self.root / name).write_bytes(b'old-' + name.encode())
            (release / name).write_bytes(b'new-' + name.encode())
        (self.root / 'room_speaker_state.json').write_text('preserve-state', encoding='utf-8')

    def powershell(self, command):
        source = "$ErrorActionPreference='Stop'; . " + ps_quote(SCRIPT) + ' -LibraryOnly; ' + command
        encoded = base64.b64encode(source.encode('utf-16-le')).decode('ascii')
        result = subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',encoded],
                                capture_output=True, timeout=20,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_install_backs_up_and_keeps_state(self):
        self.powershell('function Get-LabBoyProcesses { @() }; '
                        '$backup=Install-LabBoyRelease -AppDirectory ' + ps_quote(self.root))
        for name in NAMES:
            self.assertEqual((self.root / name).read_bytes(), b'new-' + name.encode())
            backups = list((self.root / 'build' / 'update-backups').glob('*/' + name))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), b'old-' + name.encode())
        self.assertEqual((self.root / 'room_speaker_state.json').read_text(), 'preserve-state')

    def test_missing_release_does_not_modify_existing_files(self):
        (self.root / 'build' / 'release' / NAMES[1]).unlink()
        self.powershell('$failed=$false; try { Install-LabBoyRelease -AppDirectory ' + ps_quote(self.root) +
                        ' } catch { $failed=$true }; if(-not $failed){throw "Expected failure"}')
        for name in NAMES:
            self.assertEqual((self.root / name).read_bytes(), b'old-' + name.encode())

    def test_running_process_blocks_install_without_force(self):
        self.powershell('function Get-LabBoyProcesses { [pscustomobject]@{ProcessId=99999} }; '
                        '$failed=$false; try { Install-LabBoyRelease -AppDirectory ' + ps_quote(self.root) +
                        ' } catch { $failed=$true }; if(-not $failed){throw "Expected failure"}')
        for name in NAMES:
            self.assertEqual((self.root / name).read_bytes(), b'old-' + name.encode())

    def test_process_selection_requires_this_installation_path(self):
        own = self.root / NAMES[0]
        other = self.root / 'another-app' / NAMES[0]
        self.powershell('function Get-CimInstance { @('
                        '[pscustomobject]@{Name="room_speaker_monitor.exe";ProcessId=1;ExecutablePath=' + ps_quote(own) + '},'
                        '[pscustomobject]@{Name="room_speaker_monitor.exe";ProcessId=2;ExecutablePath=' + ps_quote(other) + '},'
                        '[pscustomobject]@{Name="python.exe";ProcessId=3;CommandLine="python unrelated.py"}'
                        ') }; $selected=@(Get-LabBoyProcesses -AppDirectory ' + ps_quote(self.root) +
                        '); if($selected.Count -ne 1 -or $selected[0].ProcessId -ne 1){throw "Wrong process selected"}')

    def test_copy_failure_restores_original_executables(self):
        self.powershell('function Get-LabBoyProcesses { @() }; '
                        'function Copy-Item { param($LiteralPath,$Destination,[switch]$Force); '
                        'if($LiteralPath -like "*build\\release\\labboy_coworking_broadcast.exe"){throw "simulated failure"}; '
                        'Microsoft.PowerShell.Management\\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -Force }; '
                        '$failed=$false; try { Install-LabBoyRelease -AppDirectory ' + ps_quote(self.root) +
                        ' } catch { $failed=$true }; if(-not $failed){throw "Expected failure"}')
        for name in NAMES:
            self.assertEqual((self.root / name).read_bytes(), b'old-' + name.encode())


if __name__ == '__main__':
    unittest.main()
