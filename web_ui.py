"""ตัวควบคุมหน้าต่าง HTML/CSS ผ่าน pywebview; monitor ยังเป็น process แยก."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
import ctypes
from ctypes import wintypes
from typing import Any

import webview
import desktop_diagnostics as diagnostics
from room_config import EXAMPLE_CONFIG_PATH, ROOM_CONFIG_PATH, ROOMS, is_valid_ipv4
from credentials import read_saved_speaker_password, save_speaker_password

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None


IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
WEB_DIR = RESOURCE_DIR / "web"
LOG_FILE = APP_DIR / "logs" / "room_speaker_monitor.log"
STATE_FILE = APP_DIR / "room_speaker_state.json"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "labboy-coworking-broadcast"
PREFERENCES_FILE = CONFIG_DIR / "preferences.json"
DEFAULT_URL = "https://k-room.icit.kmutnb.ac.th/web/reserve/calendar"
POLL_SECONDS = 30
STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE = "LabboyCoworkingBroadcast"
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def load_preferences() -> dict[str, Any]:
    try:
        value = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def set_awake(enabled: bool) -> None:
    if os.name != "nt":
        return
    fn = ctypes.windll.kernel32.SetThreadExecutionState
    fn.argtypes = [wintypes.DWORD]
    fn.restype = wintypes.DWORD
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enabled else 0)
    if not fn(flags):
        raise ctypes.WinError()


def default_room_cards(rooms: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    tint = {
        "Windows": ("#E8F1FF", "#1769D2"), "iOS": ("#EFEBFF", "#6750A4"),
        "Android": ("#E7F6EC", "#257942"), "Linux": ("#FFF0DD", "#A65A00"),
    }
    return [
        {"name": name, "number": str(device.get("number", "—")),
         "ip": str(device.get("ip", "")), "audio_id": str(device.get("audio_id", 13)),
         "status": "ยังไม่มีผลทดสอบ", "status_kind": "neutral",
         "tint": tint.get(name, ("#EEF1F6", "#566174"))[0],
         "tint_text": tint.get(name, ("#EEF1F6", "#566174"))[1]}
        for name, device in rooms.items()
    ]


class BroadcastController:
    """API สำหรับ JavaScript พร้อมจัดการ monitor, Windows และสถานะหน้าจอ."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.preferences = load_preferences()
        self.schedule_url = str(self.preferences.get("schedule_url", DEFAULT_URL))
        self.startup_enabled = bool(self.preferences.get("startup_enabled", self.windows_startup_enabled()))
        self.close_to_tray = bool(self.preferences.get("close_to_tray", False))
        self.appearance = str(self.preferences.get("appearance", "light"))
        self.rooms = {name: dict(device) for name, device in ROOMS.items()}
        self.password = self.read_password()
        self._credentials_pending = False
        self._settings_pending = False
        self.process: subprocess.Popen[str] | None = None
        self.reader_thread: threading.Thread | None = None
        self.monitor_mode = "ใช้งานจริง"
        self.is_monitor_session = False
        self.started_at: datetime | None = None
        self.last_read: datetime | None = None
        self.next_poll: datetime | None = None
        self.read_count = 0
        self.last_read_count = 0
        self.booking_count = 0
        self.successes = 0
        self.failures = 0
        self.status = "กำลังเตรียมระบบ"
        self.status_kind = "blue"
        self.read_error = ""
        self.auth_error = False
        self.records: dict[str, dict[str, Any]] = {}
        self._cycle_records: dict[str, dict[str, Any]] | None = None
        self._current_booking_key: str | None = None
        self._active_audio_key: str | None = None
        self.observed_keys: set[str] = set()
        self.sent_keys: set[str] = set()
        self.shutting_down = False
        self.shutdown_error = ""
        self._shutdown_gate = threading.Lock()
        self._shutdown_complete = threading.Event()
        self.pending_restart = False
        self.seen_booking_events: set[str] = set()
        self.activities: deque[dict[str, str]] = deque(maxlen=40)
        self.log_tail: deque[str] = deque(maxlen=200)
        self.room_results = {name: {"status": "ยังไม่มีผลทดสอบ", "kind": "neutral"} for name in self.rooms}
        self.sleep_prevention = False
        self._awake_stop = threading.Event()
        self._awake_thread: threading.Thread | None = None
        self.pending_test_room: str | None = None
        self.resume_after_test = False
        self.intentional_stop = False
        self.pending_close = False
        self.window: Any = None
        self.tray_icon: Any = None
        self.last_tray_title = ""
        self.close_accepted = False
        self.initialized = False
        self._diagnostic_cancel = threading.Event()
        self._diagnostic_thread: threading.Thread | None = None
        self._diagnostic_revision = 0
        self._diagnostic_last_started = -60.0
        self.diagnostic_state: dict[str, Any] = {'running': False, 'checked_at': '', 'rows': [], 'stale': False}
        self.start_hidden = "--start-tray" in sys.argv
        self._load_sound_state()
        self._load_previous_logs()

    def _load_sound_state(self) -> None:
        """ใช้ไฟล์กันเสียงซ้ำของ monitor เพื่อแสดงผลให้ตรงกันหลังเปิดแอปใหม่."""
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                return
            for field, destination in (("triggered", self.sent_keys),
                                       ("observed_in_use", self.observed_keys)):
                for signature in state.get(field, []):
                    if not isinstance(signature, str):
                        continue
                    parts = signature.split("|")
                    if len(parts) != 4 or parts[0] != datetime.now().date().isoformat():
                        continue
                    start, end = (datetime.fromisoformat(value) for value in parts[2:])
                    destination.add(f"{parts[1]}|{start:%Y-%m-%d %H:%M}|{end:%Y-%m-%d %H:%M}")
        except (OSError, ValueError, TypeError):
            return

    def read_password(self) -> str:
        try:
            return read_saved_speaker_password() or ""
        except (OSError, AttributeError):
            return ""

    def _load_previous_logs(self) -> None:
        try:
            lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        except OSError:
            return
        for line in lines:
            self._append_activity(line, from_history=True)

    def windows_startup_enabled(self) -> bool:
        if os.name != "nt":
            return False
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
                winreg.QueryValueEx(key, STARTUP_VALUE)
            return True
        except (OSError, ImportError):
            return False

    def startup_command(self) -> str:
        if IS_FROZEN:
            parts = [sys.executable]
        else:
            pythonw = shutil.which("pyw.exe") or shutil.which("pyw")
            if pythonw:
                parts = [pythonw, "-3", str(APP_DIR / "labboy_coworking_broadcast.py")]
            else:
                python = Path(sys.executable)
                pythonw_path = python.with_name("pythonw.exe") if python.name.lower() == "python.exe" else python
                parts = [str(pythonw_path if pythonw_path.is_file() else python), str(APP_DIR / "labboy_coworking_broadcast.py")]
        if self.close_to_tray:
            parts.append("--start-tray")
        return subprocess.list2cmdline(parts)

    def _write_startup_registration(self) -> None:
        if os.name != "nt":
            return
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_KEY) as key:
            if self.startup_enabled:
                winreg.SetValueEx(key, STARTUP_VALUE, 0, winreg.REG_SZ, self.startup_command())
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_VALUE)
                except FileNotFoundError:
                    pass

    def startup(self) -> dict[str, Any]:
        """ลงทะเบียน startup และเปิด monitor จริงอัตโนมัติเมื่อมีรหัสที่บันทึกไว้."""
        if self.initialized:
            return self.get_state()
        self.initialized = True
        try:
            self._write_startup_registration()
        except (OSError, ImportError):
            pass
        if self.close_to_tray and self.ensure_tray_icon():
            if self.start_hidden and self.window:
                self.window.hide()
        if self.password:
            self.monitor_mode = "ใช้งานจริง"
            self.start_monitor(automatic=True)
        else:
            self.status = "ตั้งรหัสลำโพงก่อนเริ่มระบบ"
            self.status_kind = "amber"
        return self.get_state()

    def get_state(self) -> dict[str, Any]:
        with self.lock:
            now = datetime.now()
            if not self.shutting_down and not self.shutdown_error and self.process is not None and self.process.poll() is None:
                if self.is_monitor_session:
                    self.status = self.status if self.read_error or self.auth_error or self.shutdown_error else "กำลังตรวจตาราง"
                    if not self.read_error and not self.auth_error and not self.shutdown_error:
                        self.status_kind = "green" if self.monitor_mode == "ใช้งานจริง" else "blue"
                else:
                    self.status = "กำลังทดสอบเสียง"
                    self.status_kind = "amber"

            next_item = self._next_broadcast(now)
            runtime = "ยังไม่เริ่ม"
            if self.started_at and self.is_monitor_session and self.process and self.process.poll() is None:
                runtime = self._duration(now - self.started_at)
            room_cards = default_room_cards(self.rooms)
            for card in room_cards:
                result = self.room_results.get(card["name"])
                if result:
                    card["status"] = result["status"]
                    card["status_kind"] = result["kind"]
            self._update_tray_status()
            return {
                "running": bool(self.process and self.process.poll() is None),
                "closing": self.shutting_down,
                "diagnostics": {**self.diagnostic_state, 'rows': [dict(row) for row in self.diagnostic_state['rows']]},
                "monitor_running": bool(self.process and self.process.poll() is None and self.is_monitor_session),
                "is_live": self.monitor_mode == "ใช้งานจริง",
                "status": self.status, "status_kind": self.status_kind,
                "last_read": self.last_read.strftime("%H:%M:%S") if self.last_read else "ยังไม่อ่าน",
                "read_error": self.read_error, "auth_error": self.auth_error,
                "room_cards": room_cards,
                "bookings": [
                    {key: value for key, value in row.items() if key != "end_dt"}
                    for row in sorted(self.records.values(),
                                      key=lambda row: (row.get("start", ""), row.get("room", "")))
                    if row.get("date") == now.date().isoformat()
                ],
                "activities": list(self.activities), "logs": list(self.log_tail),
                "metrics": {"runtime": runtime, "reads": self.read_count, "bookings": self.booking_count,
                            "successes": self.successes, "failures": self.failures},
                "next_broadcast": next_item,
                "settings": {"schedule_url": self.schedule_url, "startup_enabled": self.startup_enabled,
                             "close_to_tray": self.close_to_tray, "has_password": bool(self.password),
                             "appearance": self.appearance,
                             "room_config_path": str(ROOM_CONFIG_PATH),
                             "rooms": [{"name": name, "number": str(device.get("number", "")),
                                        "ip": str(device.get("ip", "")),
                                        "audio_id": int(device.get("audio_id", 13))}
                                       for name, device in self.rooms.items()]},
                "now": now.strftime("%Y-%m-%d %H:%M:%S"),
            }

    @staticmethod
    def _duration(delta: timedelta) -> str:
        seconds = max(0, int(delta.total_seconds()))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _next_broadcast(self, now: datetime) -> dict[str, str] | None:
        candidates = [
            row for row in self.records.values()
            if row.get("observed_in_use") and row.get("end_dt")
            and row.get("status") not in {"ระงับการจอง", "ไม่ทราบสถานะ"}
            and row.get("date") == now.date().isoformat()
            and (row["end_dt"] - now).total_seconds() >= -90
            and row.get("alert") not in {"ส่งเสียงแล้ว", "ข้าม · ถูกระงับ", "ข้าม · ไม่พบสถานะใช้"}
        ]
        if (self.shutting_down or not candidates or self.monitor_mode != "ใช้งานจริง" or not self.is_monitor_session
                or not self.process or self.process.poll() is not None):
            return None
        row = min(candidates, key=lambda item: item["end_dt"])
        end = row["end_dt"]
        seconds = max(0, int((end - now).total_seconds()))
        if seconds == 0:
            seconds = max(1, int((self.next_poll - now).total_seconds())) if self.next_poll else POLL_SECONDS
            detail = "ครบเวลาแล้ว · รอรอบตรวจถัดไป"
        else:
            detail = f"ครบเวลา {end:%H:%M}"
        mins, secs = divmod(seconds, 60)
        eta = f"{mins} นาที {secs} วินาที" if mins else f"{secs} วินาที"
        return {"room": row["room"], "room_number": row.get("room_number", "—"),
                "detail": detail, "eta": eta, "end": end.strftime("%H:%M"), "seconds": str(seconds)}

    def _monitor_command(self) -> list[str]:
        if IS_FROZEN:
            monitor_exe = APP_DIR / "room_speaker_monitor.exe"
            if not monitor_exe.is_file():
                raise FileNotFoundError(f"ไม่พบไฟล์ {monitor_exe}")
            return [str(monitor_exe)]
        # ใช้ interpreter เดียวกับแอป เพื่อคง dependencies ของ virtual environment.
        if Path(sys.executable).is_file():
            executable = Path(sys.executable)
            if executable.name.casefold() == "pythonw.exe":
                executable = executable.with_name("python.exe")
            return [str(executable), str(APP_DIR / "room_speaker_monitor.py")]
        python = shutil.which("python.exe") or shutil.which("python")
        if python:
            return [python, str(APP_DIR / "room_speaker_monitor.py")]
        raise RuntimeError("ไม่พบ Python Launcher หรือ Python ใน PATH")

    def _keep_windows_awake(self) -> None:
        """ตั้งสถานะกัน Sleep จาก thread เดียวกันตลอดอายุ monitor."""
        while not self._awake_stop.is_set():
            try:
                set_awake(True)
            except (AttributeError, OSError):
                return
            self._awake_stop.wait(30)
        try:
            set_awake(False)
        except (AttributeError, OSError):
            pass

    def _start_awake_thread(self) -> None:
        if os.name != "nt" or (self._awake_thread and self._awake_thread.is_alive()):
            return
        self._awake_stop.clear()
        self.sleep_prevention = True
        self._awake_thread = threading.Thread(target=self._keep_windows_awake,
                                              name="labboy-awake", daemon=True)
        self._awake_thread.start()

    def _stop_awake_thread(self) -> None:
        self._awake_stop.set()
        thread = self._awake_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.5)
        self._awake_thread = None
        self.sleep_prevention = False

    def start_monitor(self, automatic: bool = False) -> dict[str, Any]:
        with self.lock:
            if self.shutting_down:
                return {"ok": False, "message": "กำลังปิดโปรแกรม"}
            if self.pending_test_room:
                return {"ok": False, "message": "กำลังรอทดสอบเสียง"}
            if self.process and self.process.poll() is None:
                return {"ok": True, "state": self.get_state()}
            if not self.schedule_url.startswith(("http://", "https://")):
                return {"ok": False, "message": "URL ตารางต้องขึ้นต้นด้วย http:// หรือ https://"}
            if self.monitor_mode == "ใช้งานจริง" and not self.password:
                self.status = "ตั้งรหัสลำโพงก่อนเริ่มระบบ"
                self.status_kind = "amber"
                return {"ok": False, "needs_password": True, "state": self.get_state()}
            try:
                command = self._monitor_command()
                if self.monitor_mode == "ใช้งานจริง":
                    command.append("--live")
                env = os.environ.copy()
                env.update({"SCHEDULE_URL": self.schedule_url,
                            "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
                if self.monitor_mode == "ใช้งานจริง":
                    env["SPEAKER_PASSWORD"] = self.password
                else:
                    env.pop("SPEAKER_PASSWORD", None)
                self.process = subprocess.Popen(
                    command, cwd=str(APP_DIR), env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace", bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                self.status = f"เริ่ม monitor ไม่สำเร็จ: {exc}"
                self.status_kind = "red"
                return {"ok": False, "message": str(exc)}
            self.is_monitor_session = True
            self._credentials_pending = False
            self._settings_pending = False
            self.started_at = datetime.now()
            self.read_count = self.successes = self.failures = 0
            self.read_error = ""
            self.shutdown_error = ""
            self.auth_error = False
            self.status = "กำลังเริ่มตรวจตาราง"
            self.status_kind = "green" if self.monitor_mode == "ใช้งานจริง" else "blue"
            self._invalidate_diagnostics()
            self._start_awake_thread()
            self._append_activity("เริ่มระบบตรวจตารางอัตโนมัติ", title="เริ่มระบบตรวจตาราง", subtitle="กำลังเชื่อมต่อ K-Room", kind="blue")
            self.reader_thread = threading.Thread(target=self._read_output, args=(self.process,), daemon=True)
            self.reader_thread.start()
            return {"ok": True, "state": self.get_state()}

    def _read_output(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is not None:
            for raw in process.stdout:
                line = raw.rstrip("\r\n")
                if line:
                    with self.lock:
                        self._handle_log(line)
        code = process.wait()
        with self.lock:
            if self.process is not process:
                return
            self.process = None
            self.is_monitor_session = False
            self._stop_awake_thread()
            intentional_stop = self.intentional_stop
            self.intentional_stop = False
            self.status = ("กำลังหยุดและปิดโปรแกรม" if self.shutting_down else
                           "หยุดชั่วคราว · ไม่มีการประกาศเสียง" if intentional_stop or code == 0
                           else f"ระบบหยุดด้วยข้อผิดพลาด ({code})")
            self.status_kind = "amber" if self.shutting_down or intentional_stop or code == 0 else "red"
            self._append_activity("หยุดการตรวจตาราง", title="หยุดการตรวจตาราง",
                                  subtitle="หยุดชั่วคราวตามคำสั่ง" if intentional_stop else
                                  ("ระบบหยุดทำงาน" if code == 0 else f"ออกด้วยรหัส {code}"),
                                  kind="amber" if intentional_stop or code == 0 else "red")
            test_room = self.pending_test_room
            resume = self.resume_after_test
            self.pending_test_room = None
            self.resume_after_test = False
            restart = self.pending_restart
            self.pending_restart = False
            # ตัดสินคิวขณะถือ lock เดียวกัน เพื่อให้ปุ่มหยุดยกเลิกการเริ่มต่อได้แน่นอน.
            if test_room and not self.shutting_down:
                self._launch_test_process(test_room, resume)
            elif restart and not self.shutting_down:
                self.start_monitor(automatic=True)

    def _handle_log(self, line: str) -> None:
        self.log_tail.append(line)
        timestamp_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
        timestamp = timestamp_match.group(1)[11:] if timestamp_match else datetime.now().strftime("%H:%M:%S")
        match = re.search(r"พบรายการ: ห้อง (.*?) \| (.*?)–(.*?) \| สถานะ=(.*?) สี=(.*)$", line)
        if match:
            room, start, end, status, _color = match.groups()
            key = f"{room}|{start}|{end}"
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d %H:%M")
            except ValueError:
                end_dt = None
            number = str(self.rooms.get(room, {}).get("number", "—"))
            old = self.records.get(key, {})
            if status == "กำลังใช้ห้อง":
                self.observed_keys.add(key)
            alert = "ส่งเสียงแล้ว" if key in self.sent_keys else old.get(
                "alert", "รอเริ่มใช้งาน" if status == "จองแล้ว" else "รอตรวจสถานะ")
            row = {"key": key, "room": room, "room_number": number,
                                 "start": start[-5:], "end": end[-5:], "status": status,
                                 "alert": alert, "date": start[:10],
                                 "observed_in_use": key in self.observed_keys,
                                 "end_dt": end_dt, "timestamp": timestamp}
            self._current_booking_key = key
            if self._cycle_records is None:
                self.records[key] = row
            else:
                self._cycle_records[key] = row
                if len(self._cycle_records) >= self.booking_count:
                    self.records = self._cycle_records
                    self._cycle_records = None
            event_key = f"booking:{key}"
            if event_key not in self.seen_booking_events:
                self.seen_booking_events.add(event_key)
                self._append_activity(line, timestamp=timestamp, title="ตรวจพบรายการจอง",
                                      subtitle=f"{room} · ROOM {number} · {start[-5:]}–{end[-5:]}", kind="blue")
            active_key = f"active:{key}"
            if status == "กำลังใช้ห้อง" and active_key not in self.seen_booking_events:
                self.seen_booking_events.add(active_key)
                self._append_activity(line, timestamp=timestamp, title="ตรวจพบห้องเริ่มใช้งาน",
                                      subtitle=f"{room} · ROOM {number} · {start[-5:]}–{end[-5:]}", kind="green")
        if "สรุปรายการที่อ่านได้:" in line:
            self.last_read = datetime.now()
            self.next_poll = self.last_read + timedelta(seconds=POLL_SECONDS)
            self.read_count += 1
            self.read_error = ""
            counts = [part.rsplit("=", 1)[-1].strip()
                      for part in line.split("สรุปรายการที่อ่านได้:", 1)[1].split(",")]
            self.booking_count = sum(int(value) for value in counts if value.isdigit())
            self._cycle_records = {} if self.booking_count else None
            if not self.booking_count:
                self.records.clear()
            self._current_booking_key = None
            self.last_read_count = self.booking_count
            self.status = "อ่านตารางแล้ว · ไม่พบรายการวันนี้" if self.booking_count == 0 else "กำลังตรวจตาราง"
            self.status_kind = "amber" if self.booking_count == 0 else "green"
            if self.booking_count == 0:
                self._append_activity(line, timestamp=timestamp, title="ตรวจตารางเรียบร้อย",
                                      subtitle="วันนี้ไม่พบรายการจองในห้องที่ติดตาม", kind="green")
            else:
                self._append_activity(line, timestamp=timestamp, title="ตรวจตารางเรียบร้อย",
                                      subtitle=f"พบรายการจอง {self.booking_count} รายการ", kind="green")
        skip = re.search(r"ข้ามรายการห้อง (.*?) เพราะ(.*)$", line)
        if skip:
            room, reason = skip.groups()
            alert = "ข้าม · ถูกระงับ" if "ระงับการจอง" in reason or "ระงับ" in reason else "ข้าม · ไม่พบสถานะใช้"
            self._set_alert_by_room(room, alert)
            number = str(self.rooms.get(room, {}).get("number", "—"))
            skip_key = f"skip:{self._current_booking_key}:{alert}"
            if skip_key not in self.seen_booking_events:
                self.seen_booking_events.add(skip_key)
                self._append_activity(line, timestamp=timestamp, title="ข้ามการประกาศ",
                                      subtitle=f"{room} · ROOM {number} · {self._short_reason(reason)}",
                                      kind="red" if alert == "ข้าม · ถูกระงับ" else "amber")
        ending = re.search(r"(?:\[โหมดทดลอง\] )?ถึงเวลาสิ้นสุดห้อง (.*?) เวลา (\d{2}:\d{2})", line)
        if ending:
            room, end_time = ending.groups()
            if "ไม่ได้สั่งลำโพง" in line:
                self._set_alert_by_room(room, "ครบเวลา · โหมดทดลอง")
                self._append_activity(line, timestamp=timestamp, title="ครบเวลาแล้ว · โหมดทดลอง",
                                      subtitle=f"ห้อง {room} · {end_time}", kind="blue")
            else:
                self._set_alert_by_room(room, "กำลังส่งเสียง…")
                self._append_activity(line, timestamp=timestamp, title="ตรวจพบรายการที่ครบเวลา",
                                      subtitle=f"ห้อง {room} · {end_time} · กำลังส่งเสียง", kind="amber")
        success = re.search(r"สั่งเล่นเสียงห้อง (.*?) \((.*?)\) สำเร็จ", line)
        if success:
            room = success.group(1)
            self.room_results[room] = {"status": "ส่งเสียงสำเร็จ", "kind": "green"}
            if self.is_monitor_session:
                self.successes += 1
            self.auth_error = False
            if self.is_monitor_session:
                self._set_alert_by_room(room, "ส่งเสียงแล้ว")
            self._append_activity(line, timestamp=timestamp, title="ส่งเสียงแจ้งเตือนสำเร็จ",
                                  subtitle=f"ห้อง {room} · เล่นเสียงตามกำหนดการแล้ว", kind="green")
        failure = re.search(r"ลำโพงห้อง (.*?) ตอบ HTTP (\d+):", line)
        if failure or ("ลำโพงห้อง " in line and "ERROR" in line.upper()):
            room = failure.group(1) if failure else next((name for name in self.rooms if f"ลำโพงห้อง {name}" in line), "")
            if room:
                self.room_results[room] = {"status": "ส่งเสียงไม่สำเร็จ", "kind": "red"}
                if self.is_monitor_session:
                    self.failures += 1
                    self._set_alert_by_room(room, "ส่งเสียงไม่สำเร็จ")
                auth_error = "HTTP 401" in line or "UNAUTHORIZED" in line.upper() or "AUTHENTICATION FAILED" in line.upper()
                if auth_error:
                    self.auth_error = True
                    self.status = "รหัสผ่านลำโพงไม่ผ่านการตรวจสอบ"
                    self.status_kind = "red"
                number = str(self.rooms.get(room, {}).get("number", "—"))
                self._append_activity(line, timestamp=timestamp,
                                      title="ส่งเสียงไม่สำเร็จ" if not auth_error else "ลำโพงปฏิเสธรหัสผ่าน",
                                      subtitle=f"{room} · ROOM {number} · ตรวจสอบอุปกรณ์และรหัสผ่าน", kind="red")
        if "ERROR" in line.upper() and "ลำโพงห้อง " not in line:
            self.read_error = "อ่าน K-Room หรือเปิดหน้าเว็บไม่สำเร็จ · กำลังลองใหม่"
            self.status = self.read_error
            self.status_kind = "red"
            self._append_activity(line, timestamp=timestamp, title="อ่านตารางไม่สำเร็จ",
                                  subtitle="กำลังลองใหม่ · ตรวจเครือข่ายหรือหน้า K-Room", kind="red")

    @staticmethod
    def _short_reason(reason: str) -> str:
        text = reason.strip().strip(":; ")
        if "ระงับ" in text:
            return "การจองถูกระงับ"
        if "ไม่เคยพบสถานะกำลังใช้ห้อง" in text:
            return "ไม่พบสถานะกำลังใช้ห้องก่อนหมดเวลา"
        if "แปลสีสถานะ" in text:
            return "ยังแปลสถานะจาก K-Room ไม่ได้"
        return text[:100]

    def _set_alert_by_room(self, room: str, alert: str) -> None:
        """ผูกผลกับรายการที่กำลังประมวลผล แทนการเลือกแถวสุดท้ายของห้อง."""
        pool = dict(self.records)
        pool.update(self._cycle_records or {})
        row = pool.get(self._current_booking_key or "")
        if not row or row["room"] != room:
            return
        row["alert"] = alert
        if alert == "ส่งเสียงแล้ว":
            self.sent_keys.add(row["key"])

    def _append_activity(self, raw: str, *, timestamp: str | None = None,
                         title: str | None = None, subtitle: str | None = None,
                         kind: str | None = None, from_history: bool = False) -> None:
        if title is None:
            if "สั่งเล่นเสียงห้อง " in raw and "สำเร็จ" in raw:
                title, kind = "ส่งเสียงแจ้งเตือนสำเร็จ", "green"
            elif "ลำโพงห้อง " in raw and ("ERROR" in raw.upper() or "HTTP " in raw):
                title, kind = "ส่งเสียงไม่สำเร็จ", "red"
            elif "ข้ามรายการห้อง " in raw:
                title, kind = "ข้ามการประกาศ", "amber"
            elif "ถึงเวลาสิ้นสุดห้อง " in raw:
                title, kind = "ครบเวลาแล้ว", "amber"
            elif "สรุปรายการที่อ่านได้:" in raw:
                title, kind = "ตรวจตารางเรียบร้อย", "green"
            else:
                return
            subtitle = subtitle or raw.split(" INFO ", 1)[-1].split(" WARNING ", 1)[-1]
        if not timestamp:
            match = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})", raw)
            timestamp = match.group(1) if match else datetime.now().strftime("%H:%M:%S")
        event = {"time": timestamp, "title": title or "เหตุการณ์ระบบ",
                 "subtitle": subtitle or "", "kind": kind or "blue"}
        # เก็บผลประกาศสำคัญไว้ 10 นาที; รวม heartbeat ที่เหมือนกันแม้อยู่คนละตำแหน่ง.
        if event["title"] == "ตรวจตารางเรียบร้อย":
            for previous in self.activities:
                if previous["title"] == event["title"] and previous["subtitle"] == event["subtitle"]:
                    previous["time"] = event["time"]
                    return
        if self.activities and self.activities[0]["title"] == event["title"] and self.activities[0]["subtitle"] == event["subtitle"]:
            self.activities[0]["time"] = event["time"]
            return
        if not from_history or event["title"] in {"ส่งเสียงแจ้งเตือนสำเร็จ", "ส่งเสียงไม่สำเร็จ", "ข้ามการประกาศ"}:
            protected_titles = {"ส่งเสียงแจ้งเตือนสำเร็จ", "ส่งเสียงไม่สำเร็จ", "ข้ามการประกาศ", "ลำโพงปฏิเสธรหัสผ่าน"}
            now = datetime.now()
            recent = []
            for previous in list(self.activities)[:10]:
                try:
                    age = (now - datetime.combine(now.date(), datetime.strptime(previous["time"], "%H:%M:%S").time())).total_seconds()
                except ValueError:
                    age = 601
                if previous["title"] in protected_titles and 0 <= age < 600:
                    recent.append(previous)
            self.activities.appendleft(event)
            for previous in recent:
                if previous not in list(self.activities)[:10]:
                    self.activities.remove(previous)
                    self.activities.insert(min(9, len(self.activities)), previous)

    def set_mode(self, mode: str) -> dict[str, Any]:
        if self.process and self.process.poll() is None:
            return {"ok": False, "message": "หยุดระบบก่อนเปลี่ยนโหมด"}
        if mode not in {"ทดลอง", "ใช้งานจริง"}:
            return {"ok": False, "message": "โหมดไม่ถูกต้อง"}
        self.monitor_mode = mode
        self.status = "พร้อมเริ่มตรวจตาราง · ไม่ส่งเสียง" if mode == "ทดลอง" else "พร้อมเริ่มใช้งานจริง"
        self.status_kind = "blue" if mode == "ทดลอง" else "green"
        return {"ok": True, "state": self.get_state()}

    def pause_monitor(self, *, for_transition: bool = False) -> dict[str, Any]:
        self._invalidate_diagnostics()
        if not for_transition:
            self.pending_restart = False
            self.pending_test_room = None
            self.resume_after_test = False
        process = self.process
        if process is None or process.poll() is not None:
            return {"ok": True, "state": self.get_state()}
        self.intentional_stop = True
        if not self.is_monitor_session:
            self.resume_after_test = False
        threading.Thread(target=self._terminate_tree, args=(process,), daemon=True).start()
        return {"ok": True}

    @staticmethod
    def _terminate_tree(process: subprocess.Popen[str]) -> bool:
        if process.poll() is not None:
            return True
        try:
            result = subprocess.run(["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
            if result.returncode != 0 and process.poll() is None:
                return False
            process.wait(timeout=3)
            return True
        except (OSError, subprocess.TimeoutExpired):
            # อย่าปิดแค่ process พ่อแล้วปล่อย monitor/browser ลูกค้างเงียบ ๆ.
            return process.poll() is not None

    def test_speaker(self, room: str) -> dict[str, Any]:
        if self.shutting_down or self.pending_test_room:
            return {"ok": False, "message": "กำลังเตรียมทดสอบหรือปิดโปรแกรม กรุณารอ"}
        if room not in self.rooms:
            return {"ok": False, "message": "ไม่พบห้องที่เลือก"}
        device = self.rooms[room]
        if not is_valid_ipv4(str(device.get("ip", ""))):
            return {"ok": False, "message": f"IP ห้อง {room} ยังไม่ถูกต้อง เปิดตั้งค่าอุปกรณ์แล้วเริ่มโปรแกรมใหม่"}
        if not self.password:
            return {"ok": False, "needs_password": True}
        running = bool(self.process and self.process.poll() is None and self.is_monitor_session)
        if self.process and self.process.poll() is None and not running:
            return {"ok": False, "message": "กำลังทดสอบเสียงรายการอื่นอยู่"}
        if running:
            self.pending_test_room = room
            self.resume_after_test = True
            self.pause_monitor(for_transition=True)
            return {"ok": True, "message": "หยุด monitor แล้ว จะเริ่มทดสอบและตรวจต่ออัตโนมัติ"}
        self._launch_test_process(room, resume=False)
        return {"ok": True}

    def _launch_test_process(self, room: str, resume: bool) -> None:
        device = self.rooms.get(room, {})
        try:
            command = self._monitor_command() + ["--test-speaker", room]
            env = os.environ.copy()
            env.update({"SPEAKER_PASSWORD": self.password, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
            self.process = subprocess.Popen(
                command, cwd=str(APP_DIR), env=env, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                errors="replace", bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.is_monitor_session = False
            self.resume_after_test = resume
            self.intentional_stop = False
            self.room_results[room] = {"status": "กำลังทดสอบเสียง…", "kind": "amber"}
            self.status = f"กำลังทดสอบเสียง · {room}"
            self.status_kind = "amber"
            self._append_activity("เริ่มทดสอบเสียง", title="เริ่มทดสอบเสียง", subtitle=f"{room} · ROOM {device.get('number', '—')}", kind="blue")
            confirmed = self._run_test_input(self.process)
            self.reader_thread = threading.Thread(
                target=self._read_test_output,
                args=(self.process, resume, room, confirmed), daemon=True,
            )
            self.reader_thread.start()
        except Exception as exc:
            self.room_results[room] = {"status": "เริ่มทดสอบไม่ได้", "kind": "red"}
            self.status = f"เริ่มทดสอบไม่ได้: {exc}"
            self.status_kind = "red"
            if resume:
                self.start_monitor(automatic=True)

    @staticmethod
    def _run_test_input(process: subprocess.Popen[str]) -> bool:
        try:
            if process.stdin:
                process.stdin.write("PLAY\n")
                process.stdin.flush()
                process.stdin.close()
                return True
        except (BrokenPipeError, OSError):
            pass
        return False

    def _read_test_output(self, process: subprocess.Popen[str], resume: bool,
                          room: str | None = None, confirmed: bool = True) -> None:
        if process.stdout:
            for raw in process.stdout:
                line = raw.rstrip("\r\n")
                if line:
                    with self.lock:
                        self._handle_log(line)
        code = process.wait()
        with self.lock:
            owns_process = self.process is process
            cancelled = not confirmed or (owns_process and self.intentional_stop)
            kind = "amber" if cancelled else ("green" if code == 0 else "red")
            result = "ยกเลิกการทดสอบ" if cancelled else ("ทดสอบเสียงสำเร็จ" if code == 0 else "ทดสอบเสียงไม่สำเร็จ")
            if room in self.rooms:
                # ผูกผลกับห้องที่เลือกตั้งแต่เริ่ม process ไม่พึ่งการจับข้อความ log.
                # ส่วนหัวและ sidebar ใช้ผลเดียวกัน รวมถึงกรณี stdout ไม่มีบรรทัดสำเร็จ.
                self.room_results[room] = {
                    "status": f"{result} · {datetime.now():%H:%M:%S}", "kind": kind,
                }
                self._append_activity("", title=result,
                                      subtitle=f"{room} · ROOM {self.rooms[room].get('number', '—')}", kind=kind)
            if not owns_process:
                return
            self.process = None
            self.is_monitor_session = False
            self.intentional_stop = False
            self.status = result
            self.status_kind = kind
            if resume and self.resume_after_test and not self.shutting_down:
                self.resume_after_test = False
                self.start_monitor(automatic=True)

    def save_password(self, password: str, restart: bool = False) -> dict[str, Any]:
        if not password:
            return {"ok": False, "message": "กรอกรหัสผ่านก่อนบันทึก"}
        try:
            save_speaker_password(password)
            self.password = password
            self._credentials_pending = bool(self.process and self.process.poll() is None and self.is_monitor_session)
            self._invalidate_diagnostics()
            self._append_activity("บันทึกรหัสลำโพง", title="บันทึกรหัสลำโพงแล้ว",
                                  subtitle="เก็บใน Windows Credential Manager", kind="green")
            if self.process and self.process.poll() is None:
                if restart and self.is_monitor_session:
                    self.pending_restart = True
                    self.pause_monitor(for_transition=True)
                return {"ok": True, "message": "บันทึกรหัสแล้ว" +
                        (" · กำลังเริ่มระบบใหม่" if restart else " · ใช้เมื่อเริ่มตรวจครั้งถัดไป")}
            result = self.start_monitor(automatic=True)
            return {"ok": result.get("ok", False), "message": "บันทึกรหัสแล้ว", "state": self.get_state()}
        except (OSError, AttributeError) as exc:
            return {"ok": False, "message": str(exc)}

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = str(payload.get("schedule_url", self.schedule_url)).strip()
        if not url.startswith(("http://", "https://")):
            return {"ok": False, "message": "URL ต้องขึ้นต้นด้วย http:// หรือ https://"}
        devices = payload.get("rooms")
        updated_rooms = self.rooms
        if devices is not None:
            if not isinstance(devices, list) or not devices:
                return {"ok": False, "message": "ต้องมีห้องอย่างน้อยหนึ่งห้อง"}
            updated_rooms = {}
            for item in devices:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                number = str(item.get("number", "")).strip()
                ip = str(item.get("ip", "")).strip()
                try:
                    audio_id = int(item.get("audio_id", 13))
                except (TypeError, ValueError):
                    return {"ok": False, "message": f"Audio ID ของห้อง {name} ต้องเป็นตัวเลข"}
                if not name or not number or (ip and not is_valid_ipv4(ip)) or not 1 <= audio_id <= 128:
                    return {"ok": False, "message": f"ตรวจชื่อห้อง หมายเลขห้อง IP หรือ Audio ID ของ {name or 'รายการ'}"}
                if name in updated_rooms:
                    return {"ok": False, "message": f"ชื่อห้อง {name} ซ้ำกัน"}
                updated_rooms[name] = {"number": number, "ip": ip, "audio_id": audio_id}
            if not updated_rooms:
                return {"ok": False, "message": "ไม่พบรายการห้องที่ถูกต้อง"}
        diagnostic_changed = url != self.schedule_url or updated_rooms != self.rooms
        self.schedule_url = url
        self.startup_enabled = bool(payload.get("startup_enabled", self.startup_enabled))
        self.close_to_tray = bool(payload.get("close_to_tray", self.close_to_tray))
        self.appearance = str(payload.get("appearance", self.appearance))
        if self.appearance not in {"light", "dark", "high_contrast"}:
            self.appearance = "light"
        self.rooms = {name: dict(device) for name, device in updated_rooms.items()}
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PREFERENCES_FILE.write_text(json.dumps({
                "startup_enabled": self.startup_enabled,
                "close_to_tray": self.close_to_tray,
                "appearance": self.appearance,
                "schedule_url": self.schedule_url,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            if devices is not None:
                ROOM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                ROOM_CONFIG_PATH.write_text(json.dumps(self.rooms, ensure_ascii=False, indent=2), encoding="utf-8")
            self._write_startup_registration()
        except (OSError, ImportError) as exc:
            return {"ok": False, "message": str(exc)}
        if self.close_to_tray:
            self.ensure_tray_icon()
        elif self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        if diagnostic_changed:
            self._settings_pending = bool(self.process and self.process.poll() is None and self.is_monitor_session)
            self._invalidate_diagnostics()
        deferred = bool(self.process and self.process.poll() is None)
        suffix = " · หยุดแล้วเริ่มระบบใหม่เพื่อใช้ URL/อุปกรณ์ที่แก้" if deferred else ""
        return {"ok": True, "message": "บันทึกการตั้งค่าแล้ว" + suffix,
                "state": self.get_state()}

    def clear_activity(self) -> dict[str, bool]:
        with self.lock:
            self.activities.clear()
        return {"ok": True}

    def _invalidate_diagnostics(self) -> None:
        self._diagnostic_revision += 1
        if self.diagnostic_state['rows'] or self.diagnostic_state['running']:
            self.diagnostic_state['stale'] = True

    def restart_monitor(self) -> dict[str, Any]:
        """ใช้หลังผู้ใช้ยืนยันเท่านั้น ไม่เปลี่ยนโหมดหรือกฎประกาศเสียง."""
        if self.shutting_down:
            return {'ok': False, 'message': 'กำลังปิดโปรแกรม'}
        if self.pending_test_room or (self.process and self.process.poll() is None and not self.is_monitor_session):
            return {'ok': False, 'message': 'รอการทดสอบเสียงเสร็จก่อนเริ่มตัวตรวจใหม่'}
        if self.pending_restart:
            return {'ok': True, 'message': 'กำลังเริ่มตัวตรวจใหม่'}
        if self.process and self.process.poll() is None:
            self.pending_restart = True
            self.pause_monitor(for_transition=True)
            return {'ok': True, 'message': 'กำลังหยุดแล้วเริ่มตัวตรวจด้วยโหมดเดิม'}
        return self.start_monitor(automatic=False)

    def start_diagnostics(self) -> dict[str, Any]:
        """เริ่มตรวจแบบอ่านอย่างเดียว โดยไม่หยุด monitor หรือสั่งเสียง."""
        if self.shutting_down:
            return {'ok': False, 'message': 'กำลังปิดโปรแกรม'}
        if self.diagnostic_state['running']:
            return {'ok': True, 'message': 'กำลังตรวจระบบอยู่'}
        remaining = 60 - (time.monotonic() - self._diagnostic_last_started)
        if remaining > 0:
            return {'ok': False, 'message': f'ตรวจซ้ำได้อีก {int(remaining) + 1} วินาที เพื่อไม่ตรวจรหัสอุปกรณ์ถี่เกินไป'}
        self._diagnostic_cancel = threading.Event()
        self._diagnostic_last_started = time.monotonic()
        self.diagnostic_state = {'running': True, 'checked_at': '', 'rows': [], 'stale': False}
        snapshot = {'url': self.schedule_url, 'rooms': {name: dict(device) for name, device in self.rooms.items()},
                    'password': self.password, 'username': os.environ.get('SPEAKER_USERNAME', 'admin'),
                    'revision': self._diagnostic_revision}
        self._diagnostic_thread = threading.Thread(target=self._run_diagnostics,
            args=(snapshot, self._diagnostic_cancel), name='labboy-diagnostics', daemon=True)
        self._diagnostic_thread.start()
        return {'ok': True}

    def _run_diagnostics(self, snapshot: dict[str, Any], cancel: threading.Event) -> None:
        def publish(item: dict[str, str]) -> None:
            with self.lock:
                if not cancel.is_set() and not self.shutting_down:
                    self.diagnostic_state['rows'].append(item)

        try:
            config = diagnostics.check_configuration(snapshot['url'], snapshot['rooms'])
            publish(config)
            try:
                command = self._monitor_command()
                present = Path(command[0]).is_file() and (IS_FROZEN or Path(command[-1]).is_file())
            except (OSError, RuntimeError):
                present = False
            publish(diagnostics.row('files', 'ไฟล์ตัวตรวจตาราง', 'green' if present else 'red',
                'พบไฟล์ที่ใช้เริ่มตัวตรวจตาราง' if present else 'ไฟล์ตัวตรวจไม่ครบ ให้ใช้ชุดอัปเดตที่มี EXE ทั้งสองไฟล์',
                '' if present else 'installation'))
            with self.lock:
                running = bool(self.process and self.process.poll() is None)
                recent = self.read_count > 0 and self.last_read and (datetime.now() - self.last_read).total_seconds() <= 90
                if running and self.is_monitor_session and self._settings_pending:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'amber',
                        'มี URL หรืออุปกรณ์ใหม่ที่บันทึกแล้ว แต่ตัวตรวจรอบนี้ยังใช้ค่าเดิม เริ่มตัวตรวจใหม่เพื่อใช้ค่าที่บันทึก', 'restart')
                elif running and self.is_monitor_session and self._credentials_pending:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'amber',
                        'มีรหัสใหม่ที่บันทึกแล้ว แต่ตัวตรวจรอบนี้ยังใช้รหัสเดิม เริ่มตัวตรวจใหม่เพื่อใช้รหัสที่บันทึก', 'restart')
                elif running and self.is_monitor_session and recent and not self.read_error:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'green',
                        f'ตัวตรวจทำงาน อ่านสำเร็จล่าสุด {self.last_read:%H:%M:%S}')
                elif running and self.is_monitor_session and not self.read_error and self.started_at and self.read_count == 0 and (datetime.now() - self.started_at).total_seconds() < 45:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'blue',
                        'ตัวตรวจเริ่มทำงานแล้ว กำลังรอผลอ่านรอบแรก ตรวจสถานะอีกครั้งหลังเริ่มระบบสักครู่', 'retry')
                elif running and self.is_monitor_session:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'amber',
                        'ตัวตรวจยังทำงาน แต่ยังไม่มีผลอ่านล่าสุดที่ยืนยันได้ ระบบเดิมจะลองใหม่ตามรอบ หากยังไม่กลับมาจึงเริ่มตัวตรวจใหม่', 'restart')
                elif running:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'blue',
                        'กำลังทดสอบเสียงอยู่ รอเสร็จแล้วตรวจสถานะอีกครั้ง', 'retry')
                else:
                    item = diagnostics.row('monitor', 'การอ่านรายการจองจริง', 'amber',
                        'ตัวตรวจตารางหยุดอยู่ การตรวจระบบนี้จะไม่เริ่มประกาศให้อัตโนมัติ', 'start')
            publish(item)
            if config['kind'] != 'red' and not cancel.is_set():
                for result in diagnostics.probe_calendar(snapshot['url'], cancel):
                    publish(result)
            for name, device in snapshot['rooms'].items():
                if cancel.is_set():
                    break
                publish(diagnostics.probe_speaker(name, device, snapshot['password'], cancel,
                                                  username=snapshot.get('username', 'admin')))
        except Exception:
            # ไม่ส่ง exception ดิบที่อาจมี URL/รหัสผ่านกลับไปยัง JavaScript.
            publish(diagnostics.row('unexpected', 'ผลตรวจระบบ', 'red', 'ตรวจระบบไม่ครบ ลองตรวจใหม่หรือเปิดบันทึกให้ผู้ดูแลตรวจสอบ', 'logs'))
        finally:
            with self.lock:
                if not cancel.is_set() and not self.shutting_down:
                    self.diagnostic_state['running'] = False
                    self.diagnostic_state['checked_at'] = datetime.now().strftime('%H:%M:%S')
                    self.diagnostic_state['stale'] = snapshot['revision'] != self._diagnostic_revision

    def open_logs(self) -> dict[str, Any]:
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.startfile(str(LOG_FILE.parent))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(LOG_FILE.parent)])
            else:
                subprocess.Popen(["xdg-open", str(LOG_FILE.parent)])
            return {"ok": True}
        except (OSError, AttributeError) as exc:
            return {"ok": False, "message": str(exc)}

    def hide_window(self) -> dict[str, bool]:
        if self.window:
            self.ensure_tray_icon()
            self.window.hide()
        return {"ok": True}

    def show_window(self) -> None:
        if self.window:
            self.window.show()
            self.window.restore()

    def ensure_tray_icon(self) -> bool:
        if self.tray_icon is not None:
            return True
        if pystray is None or Image is None or os.name != "nt":
            return False
        try:
            icon_path = RESOURCE_DIR / "logo_broadcast.png"
            if icon_path.is_file():
                image = Image.open(icon_path).convert("RGBA").resize((64, 64))
            else:
                image = Image.new("RGBA", (64, 64), "#007AFF")
                ImageDraw.Draw(image).text((22, 20), "L", fill="white")
            menu = pystray.Menu(
                pystray.MenuItem("เปิดหน้าต่าง", lambda _icon, _item: self.show_window(), default=True),
                pystray.MenuItem("ออกจากโปรแกรม", lambda _icon, _item: self.request_exit_from_tray()),
            )
            self.tray_icon = pystray.Icon("labboy-coworking-broadcast", image,
                                          "LabBoy Coworking · พร้อมทำงาน", menu)
            self.tray_icon.run_detached()
            self._update_tray_status()
            return True
        except Exception:
            self.tray_icon = None
            return False

    def _update_tray_status(self) -> None:
        if not self.tray_icon or not Image:
            return
        title = f"LabBoy Coworking · {self.status}"[:120]
        signature = f"{self.status_kind}|{title}"
        if signature == self.last_tray_title:
            return
        self.last_tray_title = signature
        try:
            icon_path = RESOURCE_DIR / "logo_broadcast.png"
            picture = (Image.open(icon_path).convert("RGBA").resize((64, 64))
                       if icon_path.is_file() else Image.new("RGBA", (64, 64), "#0055B8"))
            tint = {"red": "#C62828", "amber": "#A64B00", "green": "#1D7A3E"}.get(self.status_kind, "#0055B8")
            ImageDraw.Draw(picture).ellipse((42, 42, 63, 63), fill=tint, outline="white", width=3)
            self.tray_icon.icon = picture
            self.tray_icon.title = title
        except (OSError, AttributeError):
            pass

    def request_exit_from_tray(self) -> None:
        if self.process and self.process.poll() is None and self.window:
            self._queue_close_confirmation()
        else:
            self.confirm_exit()

    def _queue_close_confirmation(self) -> None:
        with self.lock:
            if self.pending_close or self.shutting_down:
                return
            self.pending_close = True

        def show_prompt() -> None:
            try:
                self.show_window()
                if self.window:
                    # FormClosing ต้องคืนค่าให้ UI thread ก่อนเรียก WebView/JavaScript.
                    self.window.evaluate_js("window.showCloseConfirm(); undefined;")
            except Exception:
                self.cancel_exit()

        threading.Thread(target=show_prompt, name="labboy-close-prompt", daemon=True).start()

    def cancel_exit(self) -> dict[str, bool]:
        with self.lock:
            self.pending_close = False
        return {"ok": True}

    def confirm_exit(self) -> dict[str, bool]:
        with self.lock:
            if self.shutting_down:
                return {"ok": True, "closing": True}
            self.shutting_down = True
            self._diagnostic_cancel.set()
            self.diagnostic_state['running'] = False
            self.pending_close = False
            self.pending_test_room = None
            self.resume_after_test = self.pending_restart = False
            self.status = "กำลังหยุดและปิดโปรแกรม"
            self.status_kind = "amber"
        # Bridge คืนคำตอบทันที ไม่รอ taskkill หรือ destroy_window/WinForms.Invoke.
        threading.Thread(target=self._finish_exit, name="labboy-shutdown", daemon=True).start()
        return {"ok": True, "closing": True}

    def _finish_exit(self) -> None:
        if self._shutdown():
            self.close_accepted = True
            if self.window:
                self.window.destroy()
        else:
            with self.lock:
                self.shutting_down = False
                self.shutdown_error = "หยุดตัวตรวจตารางไม่สำเร็จ · กรุณาลองปิดอีกครั้ง"
                self.status = self.shutdown_error
                self.status_kind = "red"

    def _on_closing(self) -> bool:
        if self.close_accepted:
            return True
        if self.shutting_down:
            return False
        if self.close_to_tray:
            def hide_or_close() -> None:
                if self.ensure_tray_icon() and self.window:
                    self.window.hide()
                elif self.process and self.process.poll() is None:
                    self._queue_close_confirmation()
                else:
                    self.confirm_exit()
            threading.Thread(target=hide_or_close, name="labboy-hide-window", daemon=True).start()
            return False
        if self.process and self.process.poll() is None:
            self._queue_close_confirmation()
            return False
        self.confirm_exit()
        return False

    def _shutdown(self) -> bool:
        # เรียกซ้ำได้จาก worker และ finally โดยไม่หยุด process/ถาดระบบซ้ำ.
        with self._shutdown_gate:
            if self._shutdown_complete.is_set():
                return True
            with self.lock:
                self.shutting_down = True
                self._diagnostic_cancel.set()
                self.diagnostic_state['running'] = False
                self.pending_test_room = None
                self.resume_after_test = self.pending_restart = False
                self.intentional_stop = True
                process = self.process
            if process and process.poll() is None and not self._terminate_tree(process):
                return False
            reader = self.reader_thread
            if reader and reader is not threading.current_thread():
                reader.join(timeout=2)
            self._stop_awake_thread()
            if self.tray_icon is not None:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
                self.tray_icon = None
            self._shutdown_complete.set()
            return True


class DesktopAPI:
    """เปิดเผยเฉพาะคำสั่งหน้าจอ ไม่ส่งตัวอ่าน Credential หรือ Popen ผ่าน bridge."""

    def __init__(self, controller: BroadcastController) -> None:
        self._controller = controller

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        with self._controller.lock:
            if self._controller.shutting_down and name != "get_state":
                return {"ok": False, "message": "กำลังปิดโปรแกรม"}
            return getattr(self._controller, name)(*args, **kwargs)

    def startup(self) -> dict[str, Any]:
        return self._call("startup")

    def get_state(self) -> dict[str, Any]:
        return self._call("get_state")

    def start_monitor(self) -> dict[str, Any]:
        return self._call("start_monitor")

    def pause_monitor(self) -> dict[str, Any]:
        return self._call("pause_monitor")

    def set_mode(self, mode: str) -> dict[str, Any]:
        return self._call("set_mode", mode)

    def test_speaker(self, room: str) -> dict[str, Any]:
        return self._call("test_speaker", room)

    def save_password(self, password: str, restart: bool = False) -> dict[str, Any]:
        return self._call("save_password", password, restart)

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("save_settings", payload)

    def clear_activity(self) -> dict[str, bool]:
        return self._call("clear_activity")

    def open_logs(self) -> dict[str, Any]:
        return self._call("open_logs")

    def confirm_exit(self) -> dict[str, bool]:
        # ปล่อย lock ขณะรอ child process ปิด เพื่อไม่ขวาง reader thread.
        return self._controller.confirm_exit()

    def cancel_exit(self) -> dict[str, bool]:
        return self._controller.cancel_exit()

    def start_diagnostics(self) -> dict[str, Any]:
        return self._call('start_diagnostics')

    def restart_monitor(self) -> dict[str, Any]:
        return self._call('restart_monitor')


def run() -> None:
    if not WEB_DIR.joinpath("index.html").is_file():
        raise FileNotFoundError(f"ไม่พบไฟล์ UI: {WEB_DIR / 'index.html'}")
    mutex_handle = None
    if os.name == "nt":
        kernel = ctypes.windll.kernel32
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        mutex_handle = kernel.CreateMutexW(None, True, "Local\\LabBoyCoworkingBroadcastGui")
        if not mutex_handle:
            raise ctypes.WinError()
        if kernel.GetLastError() == 183:
            kernel.CloseHandle(mutex_handle)
            raise RuntimeError("หน้าต่างโปรแกรมเปิดอยู่แล้ว")
    controller = BroadcastController()
    width, height = 1280, 940
    if os.name == "nt":
        try:
            width = min(width, ctypes.windll.user32.GetSystemMetrics(0) - 40)
            height = min(height, ctypes.windll.user32.GetSystemMetrics(1) - 90)
        except (AttributeError, OSError):
            pass
    window = webview.create_window(
        "labboy-coworking-broadcast", str(WEB_DIR / "index.html"),
        js_api=DesktopAPI(controller), width=width, height=height,
        min_size=(min(940, width), min(620, height)), resizable=True, confirm_close=False,
        background_color="#F2F2F7",
    )
    controller.window = window
    window.events.closing += lambda *_args: controller._on_closing()
    def on_minimized(*_args: Any) -> None:
        if controller.close_to_tray and controller.ensure_tray_icon():
            window.hide()
    def set_native_icon(*_args: Any) -> None:
        if os.name == "nt":
            try:
                from System.Drawing import Icon
                window.native.Icon = Icon(str(RESOURCE_DIR / "labboy-coworking-broadcast.ico"))
            except (ImportError, AttributeError, OSError):
                pass
    window.events.before_show += set_native_icon
    window.events.minimized += on_minimized
    try:
        webview.start(controller.startup, gui="edgechromium", debug=False, http_server=True)
    finally:
        controller._shutdown()
        if mutex_handle:
            ctypes.windll.kernel32.CloseHandle(mutex_handle)
