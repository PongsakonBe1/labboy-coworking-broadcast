"""โหลดรายการห้องและลำโพงจากไฟล์ตั้งค่าของบัญชี Windows ปัจจุบัน."""

from __future__ import annotations

import json
import ipaddress
import os
from pathlib import Path
from typing import Any


APP_CONFIG_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "labboy-coworking-broadcast"
ROOM_CONFIG_PATH = APP_CONFIG_DIR / "room_devices.json"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().with_name("room_devices.example.json")


def is_valid_ipv4(value: str) -> bool:
    """ตรวจว่า address เป็น IPv4 ก่อนนำไปสร้าง URL คำสั่งลำโพง."""
    try:
        ipaddress.IPv4Address(value)
        return True
    except ipaddress.AddressValueError:
        return False

# ใช้เฉพาะเมื่อยังไม่มีไฟล์ตั้งค่า ส่วน IP ว่างทำให้ไม่สามารถสั่งลำโพงผิดเครื่องได้
EMPTY_ROOMS: dict[str, dict[str, Any]] = {
    "Windows": {"number": "303", "ip": "", "audio_id": 13},
    "iOS": {"number": "304", "ip": "", "audio_id": 13},
    "Android": {"number": "305", "ip": "", "audio_id": 13},
    "Linux": {"number": "306", "ip": "", "audio_id": 13},
}


def load_rooms() -> dict[str, dict[str, Any]]:
    """อ่าน mapping ห้องจาก AppData และคืน mapping ว่างที่ปลอดภัยเมื่อไฟล์ผิดรูปแบบ."""
    if not ROOM_CONFIG_PATH.is_file():
        return {name: dict(device) for name, device in EMPTY_ROOMS.items()}
    try:
        raw = json.loads(ROOM_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {name: dict(device) for name, device in EMPTY_ROOMS.items()}
    if not isinstance(raw, dict) or not raw:
        return {name: dict(device) for name, device in EMPTY_ROOMS.items()}

    rooms: dict[str, dict[str, Any]] = {}
    for raw_name, raw_device in raw.items():
        name = str(raw_name).strip()
        if not name or not isinstance(raw_device, dict):
            continue
        number = str(raw_device.get("number", "")).strip()
        ip = str(raw_device.get("ip", "")).strip()
        try:
            audio_id = int(raw_device.get("audio_id", 13))
        except (TypeError, ValueError):
            audio_id = 13
        rooms[name] = {"number": number, "ip": ip, "audio_id": audio_id}
    return rooms or {name: dict(device) for name, device in EMPTY_ROOMS.items()}


ROOMS = load_rooms()
