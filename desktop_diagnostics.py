"""ตรวจระบบแบบอ่านอย่างเดียว แยกจากกฎประกาศเสียงและรูปแบบ log ของ monitor."""
from __future__ import annotations

import time
import json
from urllib.parse import urlsplit
from typing import Any

from bs4 import BeautifulSoup
import requests
from requests.auth import HTTPDigestAuth

from room_config import is_valid_ipv4

MAX_PAGE_BYTES = 512 * 1024
DEVICE_CAPABILITIES_PATH = '/ISAPI/Event/triggers/notifications/AudioAlarm/capabilities?format=json'


def row(key: str, title: str, kind: str, detail: str, action: str = '') -> dict[str, str]:
    return {'key': key, 'title': title, 'kind': kind, 'detail': detail, 'action': action}


def check_configuration(url: str, rooms: dict[str, dict[str, Any]]) -> dict[str, str]:
    try:
        parts = urlsplit(url)
        valid_url = parts.scheme in {'http', 'https'} and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        valid_url = False
    if not valid_url:
        return row('config', 'การตั้งค่า', 'red', 'ตรวจ URL ตารางจองให้เป็น http หรือ https และไม่ใส่รหัสผ่านใน URL', 'settings')
    if not rooms:
        return row('config', 'การตั้งค่า', 'red', 'ยังไม่มีห้องที่ติดตาม เพิ่มห้องในหน้าตั้งค่า', 'settings')
    for name, device in rooms.items():
        try:
            valid_audio = 1 <= int(device.get('audio_id', 0)) <= 128
        except (ValueError, TypeError):
            valid_audio = False
        if not name or not device.get('number') or not is_valid_ipv4(str(device.get('ip', ''))) or not valid_audio:
            return row('config', 'การตั้งค่า', 'red', f'ตรวจชื่อ เลขห้อง IP หรือ Audio ID ของห้อง {name}', 'settings')
    return row('config', 'การตั้งค่า', 'green', f'URL และข้อมูลอุปกรณ์ {len(rooms)} ห้องมีรูปแบบถูกต้อง')


def probe_calendar(url: str, cancel) -> list[dict[str, str]]:
    """อ่าน HTML เท่านั้น ไม่เรียก monitor ไม่เปิด browser และไม่อ่านข้อมูลผู้จอง."""
    if cancel.is_set():
        return []
    title = 'การเชื่อมต่อ K‑Room'
    try:
        with requests.Session() as session:
            # ไม่ใช้ credentials ใน .netrc และไม่แนบรหัสลำโพงให้เว็บไซต์.
            session.trust_env = False
            with session.get(url, timeout=(4, 5), stream=True) as response:
                if response.status_code in (401, 403):
                    return [row('web', title, 'red', 'หน้าเว็บต้องเข้าสู่ระบบหรือไม่อนุญาตให้เข้าถึง ให้ผู้ดูแลตรวจ URL และสิทธิ์', 'settings')]
                if response.status_code != 200:
                    return [row('web', title, 'red', f'เว็บไซต์ตอบ HTTP {response.status_code} ลองตรวจอีกครั้ง หากยังเป็นซ้ำให้ติดต่อผู้ดูแล K‑Room', 'retry')]
                data = bytearray()
                deadline = time.monotonic() + 10
                for chunk in response.iter_content(8192):
                    if cancel.is_set():
                        return []
                    if len(data) + len(chunk) > MAX_PAGE_BYTES or time.monotonic() > deadline:
                        return [row('web', title, 'amber', 'หน้าเว็บตอบกลับมากหรือช้ากว่าที่ตรวจเบื้องต้นได้ ลองตรวจอีกครั้ง', 'retry')]
                    data.extend(chunk)
                soup = BeautifulSoup(bytes(data), 'html.parser')
                page = row('web', title, 'green', 'เปิดหน้าเว็บได้สำเร็จในการตรวจครั้งนี้')
                if soup.select_one('#calendar') is None:
                    return [page, row('calendar', 'ส่วนตารางจองในหน้าเว็บ', 'red',
                        'หน้าเว็บเปิดได้ แต่ไม่พบส่วนปฏิทินที่โปรแกรมรองรับ ตรวจ URL ก่อน หากเว็บเปลี่ยนรูปแบบให้ผู้พัฒนาปรับตัวอ่าน', 'settings')]
                return [page, row('calendar', 'ส่วนตารางจองในหน้าเว็บ', 'green',
                    'พบส่วนตารางจองในหน้าเว็บ การอ่านรายการจริงให้ดูผลของตัวตรวจตารางด้านบน')]
    except requests.exceptions.SSLError:
        return [row('web', title, 'red', 'ตรวจใบรับรองเว็บไซต์หรือวันเวลาของ Windows แล้วให้ผู้ดูแลเครือข่ายตรวจสอบ', 'logs')]
    except requests.Timeout:
        return [row('web', title, 'amber', 'เว็บไซต์ยังตอบไม่ทันเวลา ระบบตรวจตารางเดิมยังลองใหม่ตามรอบ ตรวจอีกครั้งได้โดยไม่หยุดระบบ', 'retry')]
    except requests.RequestException:
        return [row('web', title, 'red', 'เชื่อมต่อเว็บไซต์ไม่ได้ ตรวจเครือข่ายหรือ URL แล้วลองอีกครั้ง', 'settings')]


def probe_speaker(name: str, device: dict[str, Any], password: str, cancel, *, username: str = 'admin') -> dict[str, str]:
    """ใช้ GET capabilities ที่อุปกรณ์รุ่นปัจจุบันรองรับเท่านั้น ไม่มีคำสั่งเล่นเสียง."""
    key, title = 'speaker:' + name, 'ลำโพงห้อง ' + name
    if cancel.is_set():
        return row(key, title, 'neutral', 'ยกเลิกการตรวจแล้ว')
    ip = str(device.get('ip', ''))
    if not is_valid_ipv4(ip):
        return row(key, title, 'red', 'IP ยังไม่ถูกต้อง แก้ข้อมูลอุปกรณ์ห้องนี้ก่อน', 'settings')
    if not password:
        return row(key, title, 'amber', 'ยังไม่มีรหัสลำโพงที่บันทึกไว้ จึงยังตรวจสิทธิ์อุปกรณ์ไม่ได้', 'password')
    try:
        with requests.Session() as session:
            session.trust_env = False
            # ไม่ตาม redirect เพื่อไม่ส่งการตรวจไปอุปกรณ์หรือหน้าเข้าสู่ระบบอื่น.
            with session.get('http://' + ip + DEVICE_CAPABILITIES_PATH,
                             auth=HTTPDigestAuth(username, password), timeout=(3, 4),
                             allow_redirects=False, stream=True) as response:
                if response.status_code == 401:
                    return row(key, title, 'red', 'อุปกรณ์ปฏิเสธชื่อผู้ใช้หรือรหัสผ่าน ตรวจรหัสผู้ดูแลลำโพง', 'password')
                if response.status_code == 200:
                    content = bytearray()
                    deadline = time.monotonic() + 8
                    for chunk in response.iter_content(8192):
                        if cancel.is_set() or len(content) + len(chunk) > 64 * 1024 or time.monotonic() > deadline:
                            return row(key, title, 'amber', 'ยังอ่านข้อมูลอุปกรณ์ไม่ครบ ลองตรวจอีกครั้ง', 'retry')
                        content.extend(chunk)
                    try:
                        value = json.loads(content)
                    except (ValueError, TypeError):
                        value = None
                    if isinstance(value, dict) and isinstance(value.get('AudioAlarmCap'), dict):
                        authenticated = any(item.status_code == 401 for item in response.history) and response.request.headers.get('Authorization', '').startswith('Digest ')
                        if not authenticated:
                            return row(key, title, 'blue', 'อ่านข้อมูลอุปกรณ์ได้ แต่ปลายทางไม่ได้ขอพิสูจน์รหัส จึงยังยืนยันรหัสผ่านไม่ได้')
                        return row(key, title, 'green', 'อุปกรณ์ตอบกลับและยอมรับรหัสผ่าน การตรวจนี้ไม่เล่นเสียงหรือยืนยันไฟล์เสียง')
                    return row(key, title, 'amber', 'อุปกรณ์ตอบกลับ แต่รูปแบบข้อมูลต่างจากรุ่นที่รองรับ ให้ผู้ดูแลตรวจรุ่นอุปกรณ์', 'settings')
                return row(key, title, 'amber', f'อุปกรณ์ตอบ HTTP {response.status_code} แต่ยังยืนยันวิธีตรวจของรุ่นนี้ไม่ได้ ให้ผู้ดูแลตรวจอุปกรณ์', 'settings')
    except requests.Timeout:
        return row(key, title, 'red', 'ลำโพงไม่ตอบภายในเวลาที่ตรวจ ตรวจไฟเลี้ยง สายเครือข่าย และ IP ของห้องนี้', 'settings')
    except requests.RequestException:
        return row(key, title, 'red', 'ติดต่ออุปกรณ์ไม่ได้ ตรวจไฟเลี้ยง สายเครือข่าย และ IP ของห้องนี้', 'settings')
