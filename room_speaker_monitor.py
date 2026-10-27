"""ติดตามเวลาจองห้องจาก K-ROOM และสั่งไฟล์เสียงบนลำโพง Hikvision

ติดตั้งแพ็กเกจ:
    py -m pip install requests beautifulsoup4 playwright
สคริปต์ใช้ Microsoft Edge ที่ติดตั้งใน Windows ผ่าน Playwright

เริ่มโหมดทดลอง (ไม่ส่งคำสั่งไปยังลำโพง):
    $env:SCHEDULE_URL = "https://k-room.icit.kmutnb.ac.th/web/reserve/calendar"
    $env:SPEAKER_PASSWORD = "รหัสผ่านลำโพง"
    py .\room_speaker_monitor.py

เริ่มโหมดสั่งงานจริง:
    py .\room_speaker_monitor.py --live

ถ้าหน้าปฏิทินต้องเข้าสู่ระบบ ให้ตั้ง PLAYWRIGHT_STORAGE_STATE เป็น path
ของไฟล์ storage state ที่ได้จาก Playwright สำหรับบัญชีที่ได้รับอนุญาต
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import (
    Browser,
    Error as PlaywrightError,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)
from requests.auth import HTTPDigestAuth
from room_config import ROOMS, is_valid_ipv4


# ------------------------------ ตั้งค่า ------------------------------

SCHEDULE_URL = os.environ.get(
    "SCHEDULE_URL",
    "https://k-room.icit.kmutnb.ac.th/web/reserve/calendar",
)
SPEAKER_USERNAME = os.environ.get("SPEAKER_USERNAME", "admin")
SPEAKER_PASSWORD = os.environ.get("SPEAKER_PASSWORD", "")
STORAGE_STATE = os.environ.get("PLAYWRIGHT_STORAGE_STATE", "")

POLL_SECONDS = 30
# ยอมให้ระบบทำงานช้ากว่าเวลาจองเล็กน้อย เผื่อโหลดหน้าเว็บ/เครือข่ายล่าช้า
TRIGGER_GRACE_SECONDS = 90
PAGE_TIMEOUT_MS = 30_000
SPEAKER_TIMEOUT_SECONDS = 8
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
STATE_FILE = APP_DIR / "room_speaker_state.json"
LOCK_FILE = APP_DIR / "room_speaker_monitor.lock"
LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "room_speaker_monitor.log"
# ประเทศไทยใช้ UTC+7 และไม่มีการปรับเวลาออมแสง จึงไม่ต้องพึ่ง tzdata เพิ่ม
LOCAL_TZ = timezone(timedelta(hours=7), "Asia/Bangkok")
TIME_RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2}:\d{2})\s*(?:-|–|—|to)\s*(\d{1,2}:\d{2})(?!\d)",
    re.IGNORECASE,
)

log_handlers: list[logging.Handler] = [logging.StreamHandler()]
try:
    LOG_DIR.mkdir(exist_ok=True)
    log_handlers.append(RotatingFileHandler(
        LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8",
    ))
except OSError:
    # หากโฟลเดอร์โปรแกรมเขียนไม่ได้ ให้ระบบยังทำงานและส่ง log กลับ GUI ต่อไป
    pass
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=log_handlers,
)
log = logging.getLogger("k-room-speaker-monitor")
stop_requested = False


class MonitorAlreadyRunningError(RuntimeError):
    """แจ้งเมื่อมีตัวตรวจตารางหรือทดสอบลำโพงอีกชุดกำลังทำงาน"""


@contextmanager
def monitor_instance_lock():
    """ล็อกไฟล์แบบข้าม process เพื่อป้องกันสั่งเสียงซ้ำจากโปรแกรมที่เปิดซ้อน"""
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    handle = LOCK_FILE.open("a+b")
    locked = False
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                locked = True
            except OSError as exc:
                raise MonitorAlreadyRunningError(
                    "มีตัวตรวจตารางหรือการทดสอบลำโพงอีกชุดทำงานอยู่แล้ว"
                ) from exc
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
            except OSError as exc:
                raise MonitorAlreadyRunningError(
                    "มีตัวตรวจตารางหรือการทดสอบลำโพงอีกชุดทำงานอยู่แล้ว"
                ) from exc
        yield
    finally:
        try:
            if locked:
                if os.name == "nt":
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


# อ่าน event และ resource จาก FullCalendar v3 ที่หน้าเว็บสร้างเสร็จแล้ว
READ_CALENDAR_EVENTS = r"""(today) => {
    const $calendar = window.jQuery("#calendar");
    if (!$calendar.length || !$calendar.data("fullCalendar")) return null;

    const events = $calendar.fullCalendar("clientEvents").filter(event =>
        event.start && event.start.format("YYYY-MM-DD") === today
    );
    let resources = [];
    try { resources = $calendar.fullCalendar("getResources") || []; }
    catch (_) { resources = []; }

    const resourceMap = new Map();
    for (const resource of resources) {
        resourceMap.set(String(resource.id), resource.title || String(resource.id));
    }

    return events.map(event => {
        const ids = event.resourceIds ||
            (event.resourceId !== undefined ? [event.resourceId] : []);
        let resourceName = null;

        // FullCalendar v3 มีเมธอดตรงสำหรับหา resource ที่ผูกกับ event
        try {
            const linkedResource = $calendar.fullCalendar("getEventResource", event);
            resourceName = linkedResource
                ? (linkedResource.title || String(linkedResource.id))
                : null;
        } catch (_) {}

        // ใช้ resourceId สำรองในกรณีเมธอดข้างต้นไม่คืนค่า
        if (!resourceName && ids.length) {
            const id = String(ids[0]);
            resourceName = resourceMap.get(id) || null;
            if (!resourceName) {
                try {
                    const resource = $calendar.fullCalendar("getResourceById", ids[0]);
                    resourceName = resource ? (resource.title || String(resource.id)) : null;
                } catch (_) {}
            }
        }

        return {
            id: event.id == null ? "" : String(event.id),
            title: event.title || "",
            resource: resourceName,
            start: event.start ? event.start.format() : null,
            end: event.end ? event.end.format() : null,
            color: (() => {
                let color = event.backgroundColor || event.color || "";
                if (color) return String(color);
                // บางหน้ากำหนดสีเฉพาะ element ที่ render แล้ว ไม่ได้เก็บใน event object
                const wantedTitle = String(event.title || "").replace(/\s+/g, " ").trim();
                const rendered = Array.from(
                    document.querySelectorAll("#calendar .fc-timeline-event")
                ).find(element => {
                    const titleElement = element.querySelector(".fc-title");
                    return titleElement && titleElement.innerText
                        .replace(/\s+/g, " ").trim() === wantedTitle;
                });
                if (!rendered) return "";
                return rendered.style.backgroundColor ||
                    window.getComputedStyle(rendered).backgroundColor || "";
            })()
        };
    });
}"""


def handle_stop(signum: int, _frame: Any) -> None:
    """รับ Ctrl+C หรือสัญญาณปิดโปรแกรม แล้วหยุดหลังจบรอบปัจจุบัน"""
    global stop_requested
    stop_requested = True
    log.info("ได้รับสัญญาณ %s กำลังหยุดโปรแกรม", signum)


def load_trigger_state() -> tuple[set[str], set[str]]:
    """โหลดรายการที่สั่งเสียงแล้วและรายการที่เคยเห็นว่าเริ่มใช้งาน"""
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        today = datetime.now(LOCAL_TZ).date()
        keep_after = today - timedelta(days=2)

        def recent_keys(field: str) -> set[str]:
            keys = raw.get(field, [])
            # เก็บสถานะล่าสุดไว้ไม่กี่วัน ป้องกันไฟล์โตขึ้นเรื่อย ๆ
            return {
                key for key in keys
                if isinstance(key, str) and key[:10] >= keep_after.isoformat()
            }

        # อ่านไฟล์รุ่นเก่าที่มีเฉพาะ triggered ได้ต่อโดยไม่รีเซ็ตประวัติ
        return recent_keys("triggered"), recent_keys("observed_in_use")
    except FileNotFoundError:
        return set(), set()
    except (OSError, json.JSONDecodeError, AttributeError, TypeError):
        log.exception("อ่านไฟล์สถานะ %s ไม่สำเร็จ จะเริ่มสถานะใหม่", STATE_FILE)
        return set(), set()


def save_trigger_state(triggered: set[str], observed_in_use: set[str]) -> None:
    """บันทึกสถานะกันเล่นซ้ำและประวัติห้องที่เคยเริ่มใช้งาน"""
    temporary_file = STATE_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps({
            "triggered": sorted(triggered),
            "observed_in_use": sorted(observed_in_use),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(STATE_FILE)


def room_from_event(event: dict[str, Any]) -> str | None:
    """จับคู่จากชื่อ resource; ห้ามหาเลขห้องใน title เพราะอาจชนรหัสจอง"""
    resource = str(event.get("resource") or "").strip().casefold()
    title = BeautifulSoup(
        str(event.get("title") or ""), "html.parser"
    ).get_text(" ", strip=True).casefold()

    # Resource title เป็นชื่อแถวจริง เช่น Windows, IOS, Android หรือ Linux
    for room_name, config in ROOMS.items():
        if resource == room_name.casefold():
            return room_name

    # ใช้ชื่อห้องใน title เป็นทางสำรอง แต่ไม่ใช้เลขห้อง เพราะ title
    # อาจมีรหัสจอง เช่น 13056 ซึ่งมี substring "305" อยู่ภายใน
    for room_name in ROOMS:
        if re.search(rf"(?<![a-z]){re.escape(room_name.casefold())}(?![a-z])", title):
            return room_name
    return None


def parse_local_datetime(value: str) -> datetime:
    """แปลงวันเวลาจาก FullCalendar ให้เป็นเวลา Asia/Bangkok"""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TZ)
    return parsed.astimezone(LOCAL_TZ)


def read_bookings(page: Page) -> list[dict[str, Any]]:
    """อ่านเฉพาะรายการของวันนี้ตามเวลาไทยจาก FullCalendar"""
    soup = BeautifulSoup(page.content(), "html.parser")
    if soup.select_one("#calendar") is None:
        raise RuntimeError("ไม่พบ #calendar ในหน้าเว็บ")

    today = datetime.now(LOCAL_TZ).date()
    raw_events = page.evaluate(READ_CALENDAR_EVENTS, today.isoformat())
    if raw_events is None:
        raise RuntimeError("FullCalendar ยังไม่พร้อม")

    bookings: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    room_counts = {room_name: 0 for room_name in ROOMS}
    unmatched_samples: list[str] = []
    for event in raw_events:
        if not event.get("start") or not event.get("end"):
            continue
        # คัดวันก่อนจับคู่ห้องหรือบันทึกข้อมูล เพื่อไม่ประมวลผลรายการวันอื่น
        start = parse_local_datetime(event["start"])
        end = parse_local_datetime(event["end"])
        if start.date() != today:
            continue

        room_name = room_from_event(event)
        if room_name is None:
            # เก็บเฉพาะรหัส resource/event และเวลา ไม่ log ชื่อผู้จองหรือรายละเอียด
            if len(unmatched_samples) < 8:
                unmatched_samples.append(
                    f"resource={event.get('resource')!r}, id={event.get('id')!r}, "
                    f"start={event.get('start')!r}, end={event.get('end')!r}"
                )
            continue

        # FullCalendar event มีเวลาเริ่ม/สิ้นสุดที่ใช้วางแถบบน timeline
        color = str(event.get("color") or "").strip().lower()
        color_key = re.sub(r"\s+", "", color)
        color_states = {
            "rgb(60,141,188)": "จองแล้ว",
            "#3c8dbc": "จองแล้ว",
            "rgb(255,60,55)": "ระงับการจอง",
            "#ff3c37": "ระงับการจอง",
            "rgb(243,156,18)": "หมดเวลา",
            "#f39c12": "หมดเวลา",
            "rgb(0,166,90)": "กำลังใช้ห้อง",
            "#00a65a": "กำลังใช้ห้อง",
            "rgb(0,192,239)": "เช็คอินแล้ว",
            "#00c0ef": "เช็คอินแล้ว",
        }
        status = color_states.get(color_key, "ไม่ทราบสถานะ")
        # ใช้ห้องและช่วงเวลาเป็นลายเซ็น ไม่ผูกกับ id ที่บางครั้ง event source
        # ส่งซ้ำมาด้วย id ต่างกัน
        signature = f"{start.date().isoformat()}|{room_name}|{start.isoformat()}|{end.isoformat()}"
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        room_counts[room_name] += 1
        bookings.append({
            "room": room_name,
            "start": start,
            "end": end,
            "color": color,
            "status": status,
            "signature": signature,
        })
    if not bookings:
        log.info("ไม่พบรายการจองของวันนี้ใน 4 ห้องที่ติดตาม")
    log.info(
        "สรุปรายการที่อ่านได้: %s",
        ", ".join(f"{room}={count}" for room, count in room_counts.items()),
    )
    if unmatched_samples:
        log.info(
            "ตัวอย่าง event ที่จับคู่กับ 4 ห้องไม่ได้ (สูงสุด 8 รายการ): %s",
            "; ".join(unmatched_samples),
        )
    return bookings


def trigger_speaker(room_name: str) -> bool:
    """สั่งลำโพงให้เล่น custom audio ด้วย HTTP Digest Authentication"""
    if not SPEAKER_PASSWORD:
        log.error("ยังไม่ได้กำหนด SPEAKER_PASSWORD จึงไม่ส่งคำสั่งไปลำโพง")
        return False

    device = ROOMS[room_name]
    if not is_valid_ipv4(str(device.get("ip", ""))):
        log.error("ห้อง %s ยังไม่มี IP ลำโพง IPv4 ที่ถูกต้อง จึงไม่ส่งคำสั่ง", room_name)
        return False
    # เรียก endpoint เดียวกับที่ยืนยันจาก Network ของหน้าเว็บลำโพง
    url = (
        f"http://{device['ip']}/ISAPI/AccessControl/EventCardLinkageCfg/"
        f"CustomAudio/{device['audio_id']}/play?format=json"
    )
    auth = HTTPDigestAuth(SPEAKER_USERNAME, SPEAKER_PASSWORD)

    try:
        # หน้าเว็บลำโพงส่ง JSON ว่างมาพร้อมคำสั่ง PUT จึงต้องส่ง body นี้ด้วย
        response = requests.put(
            url,
            auth=auth,
            json={},
            timeout=SPEAKER_TIMEOUT_SECONDS,
        )
        if 200 <= response.status_code < 300:
            log.info(
                "สั่งเล่นเสียงห้อง %s (%s) สำเร็จ: HTTP %s",
                room_name, device["ip"], response.status_code,
            )
            response.close()
            return True

        log.error(
            "ลำโพงห้อง %s ตอบ HTTP %s: %s",
            room_name, response.status_code, response.text[:300],
        )
        response.close()
    except requests.Timeout:
        log.exception("หมดเวลารอตอบกลับจากลำโพงห้อง %s", room_name)
    except requests.RequestException:
        log.exception("เชื่อมต่อลำโพงห้อง %s ไม่สำเร็จ", room_name)
    return False


def poll_once(
    page: Page,
    triggered: set[str],
    observed_in_use: set[str],
    live: bool,
) -> None:
    """โหลดตารางหนึ่งรอบและตรวจ booking ที่เพิ่งสิ้นสุดภายในช่วงเผื่อเวลา"""
    # จาก HTML ที่แนบมา FullCalendar ขอข้อมูล event จาก endpoint นี้
    # รอ response โดยตรง ป้องกันอ่าน clientEvents ก่อนข้อมูลจองจะมาถึง
    with page.expect_response(
        lambda response: "/web/reserve/events" in response.url,
        timeout=PAGE_TIMEOUT_MS,
    ) as response_info:
        page.reload(wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)

    events_response = response_info.value
    if not events_response.ok:
        raise RuntimeError(
            f"โหลดรายการจองไม่สำเร็จ: HTTP {events_response.status}"
        )

    page.wait_for_function(
        'window.jQuery && window.jQuery("#calendar").data("fullCalendar")',
        timeout=PAGE_TIMEOUT_MS,
    )

    # รอคำขอข้อมูล FullCalendar จบก่อนอ่าน clientEvents
    page.wait_for_function(
        '!window.jQuery("#calendar").find(".fc-loading").is(":visible")',
        timeout=PAGE_TIMEOUT_MS,
    )

    now = datetime.now(LOCAL_TZ)
    bookings = read_bookings(page)
    for booking in bookings:
        end = booking["end"]
        key = booking["signature"]
        log.info(
            "พบรายการ: ห้อง %s | %s–%s | สถานะ=%s สี=%s",
            booking["room"],
            booking["start"].strftime("%Y-%m-%d %H:%M"),
            end.strftime("%Y-%m-%d %H:%M"),
            booking["status"],
            booking["color"] or "ไม่พบสี",
        )
        # จดจำห้องที่ K-Room เคยแสดงสถานะกำลังใช้ห้องไว้ก่อนหมดเวลา
        # เพราะหลังหมดเวลา สีของรายการอาจเปลี่ยนเป็น "หมดเวลา" ก่อนรอบตรวจถัดไป
        if booking["status"] == "กำลังใช้ห้อง" and key not in observed_in_use:
            observed_in_use.add(key)
            save_trigger_state(triggered, observed_in_use)
            log.info(
                "บันทึกสถานะใช้งานจริงของห้อง %s สำหรับรายการสิ้นสุด %s",
                booking["room"], end.strftime("%Y-%m-%d %H:%M"),
            )

        # เทียบเวลาแบบมีช่วงเผื่อ แทนการเทียบ HH:MM ตรงตัว
        # เพื่อไม่พลาดเมื่อหน้าเว็บโหลดช้าหรือรอบตรวจคลาดเคลื่อน
        age_seconds = (now - end).total_seconds()
        if end.date() != now.date() or not 0 <= age_seconds <= TRIGGER_GRACE_SECONDS:
            continue

        if key in triggered:
            continue

        # รายการถูกระงับจะไม่ส่งเสียง ส่วนสีที่ไม่รู้จักให้หยุดไว้ก่อนเพื่อกันสั่งผิด
        if booking["status"] == "ระงับการจอง":
            log.info("ข้ามรายการห้อง %s เพราะสถานะระงับการจอง", booking["room"])
            continue
        if booking["status"] == "ไม่ทราบสถานะ":
            log.warning(
                "ข้ามรายการห้อง %s เพราะยังแปลสีสถานะไม่ได้: %s",
                booking["room"], booking["color"] or "ไม่พบสี",
            )
            continue

        # ส่งเสียงเฉพาะรายการที่เคยเห็นเป็นสีเขียว "กำลังใช้ห้อง"
        # การจองที่ไม่เช็คอินหรือไม่เริ่มใช้งานจะไม่ถูกแจ้งเตือนเมื่อหมดเวลา
        if key not in observed_in_use:
            log.info(
                "ข้ามรายการห้อง %s เพราะไม่เคยพบสถานะกำลังใช้ห้องก่อนหมดเวลา",
                booking["room"],
            )
            continue

        if not live:
            log.info(
                "[โหมดทดลอง] ถึงเวลาสิ้นสุดห้อง %s เวลา %s — ไม่ได้สั่งลำโพง",
                booking["room"], end.strftime("%H:%M"),
            )
            continue

        log.info(
            "ถึงเวลาสิ้นสุดห้อง %s เวลา %s กำลังสั่งลำโพง",
            booking["room"], end.strftime("%H:%M"),
        )
        if trigger_speaker(booking["room"]):
            triggered.add(key)
            save_trigger_state(triggered, observed_in_use)


def main() -> int:
    """เริ่ม browser และตรวจสอบปฏิทินซ้ำตามช่วงเวลาที่ตั้งไว้"""
    parser = argparse.ArgumentParser(description="K-ROOM Hikvision speaker monitor")
    parser.add_argument(
        "--live",
        action="store_true",
        help="อนุญาตให้ส่งคำสั่งเล่นเสียงไปยังลำโพง (ค่าเริ่มต้นเป็นโหมดทดลอง)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="ตรวจตารางหนึ่งรอบแล้วหยุด (ใช้ทดสอบแบบไม่สั่งเสียง)",
    )
    parser.add_argument(
        "--test-speaker",
        choices=tuple(ROOMS),
        help="สั่งเล่นเสียงหนึ่งครั้งกับลำโพงห้องที่เลือก โดยไม่อ่านตาราง",
    )
    args = parser.parse_args()

    if not SCHEDULE_URL.startswith(("http://", "https://")):
        log.error("SCHEDULE_URL ไม่ใช่ URL ที่ถูกต้อง")
        return 2
    if args.live and not SPEAKER_PASSWORD:
        log.error("โหมด --live ต้องกำหนด SPEAKER_PASSWORD ก่อน")
        return 2
    if args.live and args.once:
        log.error("--once ใช้ตรวจแบบไม่สั่งเสียง กรุณาเอา --live ออก")
        return 2
    if args.live and args.test_speaker:
        log.error("เลือกได้อย่างใดอย่างหนึ่งระหว่าง --live กับ --test-speaker")
        return 2
    if args.test_speaker and not SPEAKER_PASSWORD:
        log.error("ทดสอบเสียงต้องกำหนด SPEAKER_PASSWORD ก่อน")
        return 2

    try:
        with monitor_instance_lock():
            return run_task(args)
    except MonitorAlreadyRunningError as exc:
        log.error("%s — ยกเลิกการเริ่มซ้ำ", exc)
        return 3
    except OSError:
        log.exception("สร้างหรือใช้ไฟล์ล็อกป้องกันการทำงานซ้อนไม่สำเร็จ")
        return 4


def run_task(args: argparse.Namespace) -> int:
    """ทำงานที่ผู้ใช้เลือกภายใต้ single-instance lock"""
    if args.test_speaker:
        device = ROOMS[args.test_speaker]
        if not is_valid_ipv4(str(device.get("ip", ""))):
            log.error("ห้อง %s ยังไม่มี IP ลำโพง IPv4 ที่ถูกต้อง จึงยกเลิกการทดสอบ", args.test_speaker)
            return 1
        log.warning(
            "กำลังจะเล่นเสียงหนึ่งครั้งที่ห้อง %s (%s), audio ID %s",
            args.test_speaker, device["ip"], device["audio_id"],
        )
        confirmation = input("หากพร้อม ให้พิมพ์ PLAY แล้วกด Enter: ").strip()
        if confirmation != "PLAY":
            log.info("ยกเลิกการทดสอบเสียง ไม่มีคำสั่งถูกส่ง")
            return 0
        return 0 if trigger_speaker(args.test_speaker) else 1

    signal.signal(signal.SIGINT, handle_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_stop)

    triggered, observed_in_use = load_trigger_state()
    with sync_playwright() as playwright:
        browser: Browser | None = None
        try:
            # ใช้ Microsoft Edge ที่ติดตั้งกับ Windows เพื่อตัดการดาวน์โหลด
            # Chromium แยกจาก Playwright ซึ่งอาจติด timeout ในเครือข่ายองค์กร
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context_options: dict[str, Any] = {}
            if STORAGE_STATE:
                context_options["storage_state"] = STORAGE_STATE
            context = browser.new_context(**context_options)
            page = context.new_page()
            page.set_default_timeout(PAGE_TIMEOUT_MS)
            page.goto(
                SCHEDULE_URL,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT_MS,
            )

            log.info(
                "เริ่มทำงานในโหมด %s ตรวจทุก %s วินาที",
                "จริง" if args.live else "ทดลอง (ไม่สั่งเสียง)",
                POLL_SECONDS,
            )
            while not stop_requested:
                try:
                    poll_once(page, triggered, observed_in_use, live=args.live)
                except PlaywrightTimeoutError:
                    log.exception("หมดเวลารอหน้าเว็บหรือข้อมูลปฏิทิน")
                except PlaywrightError:
                    log.exception("เกิดข้อผิดพลาดจาก browser/Playwright")
                except Exception:
                    log.exception("เกิดข้อผิดพลาดระหว่างตรวจตาราง")

                if args.once:
                    break

                # รอเป็นวินาทีสั้น ๆ เพื่อให้ Ctrl+C หยุดได้ทันที
                for _ in range(POLL_SECONDS):
                    if stop_requested:
                        break
                    time.sleep(1)
            context.close()
        except PlaywrightError:
            log.exception("เปิด browser หรือหน้า K-ROOM ไม่สำเร็จ")
            return 1
        finally:
            if browser is not None:
                browser.close()

    log.info("หยุดโปรแกรมแล้ว")
    return 0


if __name__ == "__main__":
    sys.exit(main())
