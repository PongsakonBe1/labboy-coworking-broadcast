"""หน้าควบคุม K-ROOM พร้อมธีมสว่างแบบเรียบง่าย ใช้ CustomTkinter"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
import os
import ctypes
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import font as tkfont
from tkinter import messagebox
from ctypes import wintypes

import customtkinter as ctk
from PIL import Image, ImageDraw
from room_config import EXAMPLE_CONFIG_PATH, ROOM_CONFIG_PATH, ROOMS, is_valid_ipv4

try:
    import pystray
except ImportError:
    pystray = None


IS_FROZEN = bool(getattr(sys, "frozen", False))
APP_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", APP_DIR))
MONITOR_SCRIPT = APP_DIR / "room_speaker_monitor.py"
MONITOR_EXE = APP_DIR / "room_speaker_monitor.exe"
LOGO_PATH = RESOURCE_DIR / "logo_broadcast.png"
ICON_PATH = RESOURCE_DIR / "labboy-coworking-broadcast.ico"
DEFAULT_SCHEDULE_URL = "https://k-room.icit.kmutnb.ac.th/web/reserve/calendar"

# Windows sleep-prevention flags. Keep the display policy unchanged so the
# monitor can run while the screen turns off according to the workstation policy.
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def set_system_sleep_prevention(enabled: bool) -> None:
    """ขอให้ Windows คงสถานะตื่นไว้เฉพาะช่วงที่ตัวตรวจตารางทำงาน"""
    if os.name != "nt":
        return
    kernel32 = ctypes.windll.kernel32
    set_execution_state = kernel32.SetThreadExecutionState
    set_execution_state.argtypes = [wintypes.DWORD]
    set_execution_state.restype = wintypes.DWORD
    flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if enabled else 0)
    if not set_execution_state(flags):
        raise ctypes.WinError()

# Design tokens are centralized here so light/dark palettes can be audited together.
DESIGN_TOKENS = {
    "light": {
        "colors": {
            "window_bg": "#F2F2F7", "surface": "#FFFFFF", "white_text": "#FFFFFF",
            "text_primary": "#111827", "text_secondary": "#4B5563", "text_muted": "#6B7280",
            "blue": "#0055B8", "blue_dark": "#004494", "blue_action": "#0055B8", "blue_action_hover": "#004494", "blue_pale": "#EBF3FF",
            "green": "#1D7A3E", "green_action": "#1D7A3E", "green_switch": "#248A3D", "green_pale": "#E8F8EE",
            "red": "#C62828", "red_action": "#C62828", "red_dark": "#A61F1F", "red_pale": "#FFECEB",
            "amber": "#A64B00", "amber_action": "#A64B00", "amber_dark": "#854000", "amber_pale": "#FFF4E5", "amber_border": "#A64B00",
            "border": "#767680", "card_border": "#D1D1D6", "inner_border": "#ECECEE", "log_bg": "#F8F9FA",
            "switch_track_off": "#767680", "text_dark": "#1F2937",
            "disabled_text": "#6B7280", "control_border": "#767680", "checkbox_border": "#6B7280",
            "disabled_blue_text": "#0066D6",
            "room_windows_bg": "#EAF3FF", "room_ios_bg": "#F0EDFF", "room_ios_text": "#6256C7",
            "room_android_bg": "#E8F8EE", "room_linux_bg": "#FFF1E5",
            "hover_warning": "#FFE8C7", "hover_neutral": "#E1E1E6",
            "hover_blue": "#DDEBFF", "test_button_hover": "#DCEBFF",
            "hover_green": "#D9F2E2", "alert_text": "#374151",
            "border_green": "#1D7A3E", "border_blue": "#0055B8",
            "scrollbar": "#8E8E93", "entry_bg": "#FBFCFE",
            "button_neutral": "#EEF1F5", "button_neutral_hover": "#E1E7EE",
            "green_button_hover": "#087653", "row_stripe": "#FAFAFC",
            "event_amber": "#FF9500",
        },
    },
    "dark": {
        "colors": {
            "window_bg": "#101114", "surface": "#1C1C1E", "white_text": "#FFFFFF",
            "text_primary": "#F5F5F7", "text_secondary": "#C1C1C8", "text_muted": "#AEAEB2",
            "blue": "#7BBFFF", "blue_dark": "#64B5FF", "blue_action": "#0055B8", "blue_action_hover": "#004494", "blue_pale": "#16283D",
            "green": "#82D9A1", "green_action": "#1D7A3E", "green_switch": "#30D158", "green_pale": "#173523",
            "red": "#FF7971", "red_action": "#B8332D", "red_dark": "#A61F1F", "red_pale": "#3B2022",
            "amber": "#FFB340", "amber_action": "#9A5700", "amber_dark": "#854000", "amber_pale": "#3D2D14", "amber_border": "#D49739",
            "border": "#6B6B72", "card_border": "#48484E", "inner_border": "#38383D", "log_bg": "#202124",
            "switch_track_off": "#74747B", "text_dark": "#F5F5F7",
            "disabled_text": "#C1C1C8", "control_border": "#85858C", "checkbox_border": "#85858C",
            "disabled_blue_text": "#A7C9FF",
            "room_windows_bg": "#183250", "room_ios_bg": "#2B254B", "room_ios_text": "#B6A9FF",
            "room_android_bg": "#173523", "room_linux_bg": "#3D2D14",
            "hover_warning": "#4A351A", "hover_neutral": "#38383D",
            "hover_blue": "#203B59", "test_button_hover": "#203B59",
            "hover_green": "#214A31", "alert_text": "#C1C1C8",
            "border_green": "#82D9A1", "border_blue": "#7BBFFF",
            "scrollbar": "#8E8E93", "entry_bg": "#252529",
            "button_neutral": "#343439", "button_neutral_hover": "#45454B",
            "green_button_hover": "#126B35", "row_stripe": "#232327",
            "event_amber": "#FFB340",
        },
    },
    "high_contrast": {
        "colors": {
            "window_bg": "#FFFFFF", "surface": "#FFFFFF", "white_text": "#FFFFFF",
            "text_primary": "#000000", "text_secondary": "#202124", "text_muted": "#333333",
            "blue": "#003D99", "blue_dark": "#002E75", "blue_action": "#003D99", "blue_action_hover": "#002E75", "blue_pale": "#EAF1FF",
            "green": "#006B2D", "green_action": "#006B2D", "green_switch": "#006B2D", "green_pale": "#E5F5E9",
            "red": "#B00020", "red_action": "#B00020", "red_dark": "#780014", "red_pale": "#FCE8EA",
            "amber": "#7A3E00", "amber_action": "#7A3E00", "amber_dark": "#5C2E00", "amber_pale": "#FFF1D6", "amber_border": "#7A3E00",
            "border": "#555555", "card_border": "#000000", "inner_border": "#767676", "log_bg": "#FFFFFF",
            "switch_track_off": "#555555", "text_dark": "#000000",
            "disabled_text": "#333333", "control_border": "#555555", "checkbox_border": "#555555",
            "disabled_blue_text": "#003D99",
            "room_windows_bg": "#EAF1FF", "room_ios_bg": "#F0EDFF", "room_ios_text": "#493A9A",
            "room_android_bg": "#E5F5E9", "room_linux_bg": "#FFF1D6",
            "hover_warning": "#FCE4BB", "hover_neutral": "#DDDEE2",
            "hover_blue": "#D8E6FF", "test_button_hover": "#D8E6FF",
            "hover_green": "#D5EEDB", "alert_text": "#202124",
            "border_green": "#006B2D", "border_blue": "#003D99",
            "scrollbar": "#555555", "entry_bg": "#FFFFFF",
            "button_neutral": "#EEEEF0", "button_neutral_hover": "#DDDEE2",
            "green_button_hover": "#005622", "row_stripe": "#F3F4F6",
            "event_amber": "#7A3E00",
        },
    },
    "typography": {
        "family": "IBM Plex Sans Thai", "fallback": "Arial",
        "mono_family": "Consolas", "emoji_family": "Segoe UI Emoji",
        "sizes": {
            "compact": 14, "caption": 14, "secondary": 14, "body": 15,
            "emphasis": 15, "lead": 16, "metric": 17, "room": 18,
            "control": 19, "section": 22, "title": 31,
        },
    },
    "controls": {
        "window_width": 1280, "window_height": 940,
        "min_window_width": 1200, "min_window_height": 700,
        "nav_icon": 48, "separator_width": 1, "separator_height": 20,
        "status_dot_width": 14, "banner_icon_width": 30,
        "switch_width": 48, "switch_height": 26,
        "main_button_height": 40, "credential_button_width": 164, "primary_button_width": 144,
        "compact_button_height": 36, "dialog_button_height": 42,
        "room_card_height": 104, "room_icon": 32,
        "room_filter_width": 86, "status_filter_width": 100, "sort_filter_width": 132,
        "open_log_button_width": 130, "clear_log_button_width": 50,
        "toolbar_button_height": 34, "border_width": 1,
        "timeline_dot_width": 22, "timestamp_width": 62,
        "dialog_cancel_width": 105, "dialog_save_width": 190,
        "credential_dialog_width": 470, "credential_dialog_height": 310,
        "filter_height": 36, "table_header_height": 30, "table_row_height": 40,
        "status_badge_height": 24, "checkbox": 20, "dialog_checkbox": 20,
        "entry_height": 46,
    },
    "radii": {
        "none": 0, "card": 16, "dialog_card": 20, "control": 11, "small_control": 9,
        "pill": 14, "metric": 12,
        "room_icon": 10, "room_badge": 7, "filter": 10, "table_header": 9,
        "timeline_panel": 12, "timeline_row": 8, "version_badge": 7,
        "checkbox": 5, "booking_row": 7, "status_badge": 9,
    },
}
ACTIVE_THEME = "light"
COLORS = DESIGN_TOKENS[ACTIVE_THEME]["colors"]
TYPOGRAPHY = DESIGN_TOKENS["typography"]
FONT_SIZES = TYPOGRAPHY["sizes"]
CONTROL_SIZES = DESIGN_TOKENS["controls"]
CORNER_RADII = DESIGN_TOKENS["radii"]
THEME_LABELS = {"light": "สว่าง", "dark": "มืด", "high_contrast": "คอนทราสต์สูง"}
THEME_KEYS = {label: key for key, label in THEME_LABELS.items()}

# Contrast relationships exercised by the current interface; the standalone checker reads these.
WCAG_TEXT_PAIRS = [
    ("light", "primary text on surface", "text_primary", "surface", 4.5),
    ("light", "primary text on window", "text_primary", "window_bg", 4.5),
    ("light", "primary text on log panel", "text_primary", "log_bg", 4.5),
    ("light", "secondary text on surface", "text_secondary", "surface", 4.5),
    ("light", "secondary text on window", "text_secondary", "window_bg", 4.5),
    ("light", "muted text on surface", "text_muted", "surface", 4.5),
    ("light", "blue action on pale blue", "blue", "blue_pale", 4.5),
    ("light", "blue action on surface", "blue", "surface", 4.5),
    ("light", "green status on pale green", "green", "green_pale", 4.5),
    ("light", "red status on pale red", "red", "red_pale", 4.5),
    ("light", "red status on surface", "red", "surface", 4.5),
    ("light", "amber status on pale amber", "amber", "amber_pale", 4.5),
    ("light", "amber status on surface", "amber", "surface", 4.5),
    ("light", "button text on surface", "text_dark", "surface", 4.5),
    ("light", "disabled credential text on surface", "disabled_text", "surface", 4.5),
    ("light", "disabled test text on pale blue", "disabled_blue_text", "blue_pale", 4.5),
    ("light", "alert body on pale red", "text_primary", "red_pale", 4.5),
    ("light", "alert body on pale amber", "text_primary", "amber_pale", 4.5),
    ("light", "white text on blue action", "white_text", "blue_action", 4.5),
    ("light", "white text on blue action hover", "white_text", "blue_action_hover", 4.5),
    ("light", "white text on green action", "white_text", "green_action", 4.5),
    ("light", "white text on red action", "white_text", "red_action", 4.5),
    ("light", "white text on amber action", "white_text", "amber_action", 4.5),
    ("light", "iOS room accent on room tint", "room_ios_text", "room_ios_bg", 4.5),
    ("light", "blue action on blue hover", "blue", "hover_blue", 4.5),
    ("light", "blue action on test hover", "blue", "test_button_hover", 4.5),
    ("light", "green action on green hover", "green", "hover_green", 4.5),
    ("light", "amber action on warning hover", "amber", "hover_warning", 4.5),
    ("light", "secondary text on log panel", "text_secondary", "log_bg", 4.5),
    ("light", "secondary text on entry", "text_secondary", "entry_bg", 4.5),
    ("light", "alert detail on striped row", "alert_text", "row_stripe", 4.5),
    ("light", "white text on green hover action", "white_text", "green_button_hover", 4.5),
    ("light", "white text on red hover action", "white_text", "red_dark", 4.5),
    ("light", "white text on amber hover action", "white_text", "amber_dark", 4.5),
    ("light", "primary text on neutral button", "text_primary", "button_neutral", 4.5),
    ("dark", "primary text on surface", "text_primary", "surface", 4.5),
    ("dark", "primary text on window", "text_primary", "window_bg", 4.5),
    ("dark", "primary text on log panel", "text_primary", "log_bg", 4.5),
    ("dark", "secondary text on surface", "text_secondary", "surface", 4.5),
    ("dark", "secondary text on window", "text_secondary", "window_bg", 4.5),
    ("dark", "muted text on surface", "text_muted", "surface", 4.5),
    ("dark", "blue action on pale blue", "blue", "blue_pale", 4.5),
    ("dark", "blue action on surface", "blue", "surface", 4.5),
    ("dark", "green status on pale green", "green", "green_pale", 4.5),
    ("dark", "red status on pale red", "red", "red_pale", 4.5),
    ("dark", "red status on surface", "red", "surface", 4.5),
    ("dark", "amber status on pale amber", "amber", "amber_pale", 4.5),
    ("dark", "amber status on surface", "amber", "surface", 4.5),
    ("dark", "button text on surface", "text_dark", "surface", 4.5),
    ("dark", "disabled credential text on surface", "disabled_text", "surface", 4.5),
    ("dark", "disabled test text on pale blue", "disabled_blue_text", "blue_pale", 4.5),
    ("dark", "alert body on pale red", "text_primary", "red_pale", 4.5),
    ("dark", "alert body on pale amber", "text_primary", "amber_pale", 4.5),
    ("dark", "white text on blue action", "white_text", "blue_action", 4.5),
    ("dark", "white text on blue action hover", "white_text", "blue_action_hover", 4.5),
    ("dark", "white text on green action", "white_text", "green_action", 4.5),
    ("dark", "white text on red action", "white_text", "red_action", 4.5),
    ("dark", "white text on amber action", "white_text", "amber_action", 4.5),
    ("dark", "iOS room accent on room tint", "room_ios_text", "room_ios_bg", 4.5),
    ("dark", "blue action on blue hover", "blue", "hover_blue", 4.5),
    ("dark", "blue action on test hover", "blue", "test_button_hover", 4.5),
    ("dark", "green action on green hover", "green", "hover_green", 4.5),
    ("dark", "amber action on warning hover", "amber", "hover_warning", 4.5),
    ("dark", "secondary text on log panel", "text_secondary", "log_bg", 4.5),
    ("dark", "secondary text on entry", "text_secondary", "entry_bg", 4.5),
    ("dark", "alert detail on striped row", "alert_text", "row_stripe", 4.5),
    ("dark", "white text on green hover action", "white_text", "green_button_hover", 4.5),
    ("dark", "white text on red hover action", "white_text", "red_dark", 4.5),
    ("dark", "white text on amber hover action", "white_text", "amber_dark", 4.5),
    ("dark", "primary text on neutral button", "text_primary", "button_neutral", 4.5),
    ("high_contrast", "primary text on surface", "text_primary", "surface", 4.5),
    ("high_contrast", "primary text on window", "text_primary", "window_bg", 4.5),
    ("high_contrast", "primary text on log panel", "text_primary", "log_bg", 4.5),
    ("high_contrast", "secondary text on surface", "text_secondary", "surface", 4.5),
    ("high_contrast", "secondary text on window", "text_secondary", "window_bg", 4.5),
    ("high_contrast", "muted text on surface", "text_muted", "surface", 4.5),
    ("high_contrast", "blue action on pale blue", "blue", "blue_pale", 4.5),
    ("high_contrast", "blue action on surface", "blue", "surface", 4.5),
    ("high_contrast", "green status on pale green", "green", "green_pale", 4.5),
    ("high_contrast", "red status on pale red", "red", "red_pale", 4.5),
    ("high_contrast", "red status on surface", "red", "surface", 4.5),
    ("high_contrast", "amber status on pale amber", "amber", "amber_pale", 4.5),
    ("high_contrast", "amber status on surface", "amber", "surface", 4.5),
    ("high_contrast", "button text on surface", "text_dark", "surface", 4.5),
    ("high_contrast", "disabled credential text on surface", "disabled_text", "surface", 4.5),
    ("high_contrast", "disabled test text on pale blue", "disabled_blue_text", "blue_pale", 4.5),
    ("high_contrast", "alert body on pale red", "text_primary", "red_pale", 4.5),
    ("high_contrast", "alert body on pale amber", "text_primary", "amber_pale", 4.5),
    ("high_contrast", "white text on blue action hover", "white_text", "blue_action_hover", 4.5),
    ("high_contrast", "white text on green hover action", "white_text", "green_button_hover", 4.5),
    ("high_contrast", "white text on red hover action", "white_text", "red_dark", 4.5),
    ("high_contrast", "white text on amber hover action", "white_text", "amber_dark", 4.5),
    ("high_contrast", "iOS accent on room tint", "room_ios_text", "room_ios_bg", 4.5),
    ("high_contrast", "blue action on blue hover", "blue", "hover_blue", 4.5),
    ("high_contrast", "blue action on test hover", "blue", "test_button_hover", 4.5),
    ("high_contrast", "green action on hover", "green", "hover_green", 4.5),
    ("high_contrast", "amber action on hover", "amber", "hover_warning", 4.5),
    ("high_contrast", "secondary text on log panel", "text_secondary", "log_bg", 4.5),
    ("high_contrast", "secondary text on entry", "text_secondary", "entry_bg", 4.5),
    ("high_contrast", "white text on blue action", "white_text", "blue_action", 4.5),
    ("high_contrast", "white text on green action", "white_text", "green_action", 4.5),
    ("high_contrast", "white text on red action", "white_text", "red_action", 4.5),
    ("high_contrast", "white text on amber action", "white_text", "amber_action", 4.5),
    ("high_contrast", "alert text on striped row", "alert_text", "row_stripe", 4.5),
    ("high_contrast", "primary text on neutral button", "text_primary", "button_neutral", 4.5),
]
WCAG_EDGE_PAIRS = [
    ("light", "control border on surface", "control_border", "surface", 3.0),
    ("light", "control border on log panel", "control_border", "log_bg", 3.0),
    ("light", "switch off track on surface", "switch_track_off", "surface", 3.0),
    ("light", "checkbox border on surface", "checkbox_border", "surface", 3.0),
    ("light", "amber action border on pale amber", "amber_border", "amber_pale", 3.0),
    ("light", "blue action border on pale blue", "border_blue", "blue_pale", 3.0),
    ("light", "green action border on pale green", "border_green", "green_pale", 3.0),
    ("light", "blue action border on hover", "border_blue", "hover_blue", 3.0),
    ("light", "control border on entry", "control_border", "entry_bg", 3.0),
    ("light", "active switch track on surface", "green_switch", "surface", 3.0),
    ("light", "scrollbar thumb on log panel", "scrollbar", "log_bg", 3.0),
    ("dark", "control border on surface", "control_border", "surface", 3.0),
    ("dark", "control border on log panel", "control_border", "log_bg", 3.0),
    ("dark", "switch off track on surface", "switch_track_off", "surface", 3.0),
    ("dark", "checkbox border on surface", "checkbox_border", "surface", 3.0),
    ("dark", "amber action border on pale amber", "amber_border", "amber_pale", 3.0),
    ("dark", "blue action border on pale blue", "border_blue", "blue_pale", 3.0),
    ("dark", "green action border on pale green", "border_green", "green_pale", 3.0),
    ("dark", "blue action border on hover", "border_blue", "hover_blue", 3.0),
    ("dark", "control border on entry", "control_border", "entry_bg", 3.0),
    ("dark", "active switch track on surface", "green_switch", "surface", 3.0),
    ("dark", "scrollbar thumb on log panel", "scrollbar", "log_bg", 3.0),
    ("high_contrast", "card border on surface", "card_border", "surface", 3.0),
    ("high_contrast", "control border on surface", "control_border", "surface", 3.0),
    ("high_contrast", "control border on log panel", "control_border", "log_bg", 3.0),
    ("high_contrast", "switch off track on surface", "switch_track_off", "surface", 3.0),
    ("high_contrast", "checkbox border on surface", "checkbox_border", "surface", 3.0),
    ("high_contrast", "amber action border on pale amber", "amber_border", "amber_pale", 3.0),
    ("high_contrast", "blue action border on pale blue", "border_blue", "blue_pale", 3.0),
    ("high_contrast", "green action border on pale green", "border_green", "green_pale", 3.0),
    ("high_contrast", "active switch track on surface", "green_switch", "surface", 3.0),
    ("high_contrast", "scrollbar thumb on log panel", "scrollbar", "log_bg", 3.0),
]

# Compatibility aliases keep the existing state/monitor code independent of the theme map.
BG = COLORS["window_bg"]
WHITE = COLORS["surface"]
TEXT = COLORS["text_primary"]
MUTED = COLORS["text_secondary"]
BLUE = COLORS["blue"]
BLUE_DARK = COLORS["blue_dark"]
BLUE_PALE = COLORS["blue_pale"]
GREEN = COLORS["green"]
GREEN_SWITCH = COLORS["green_switch"]
GREEN_PALE = COLORS["green_pale"]
RED = COLORS["red"]
RED_PALE = COLORS["red_pale"]
AMBER = COLORS["amber"]
AMBER_PALE = COLORS["amber_pale"]
AMBER_BORDER = COLORS["amber_border"]
BORDER = COLORS["border"]
INNER_BORDER = COLORS["inner_border"]
LOG_BG = COLORS["log_bg"]
FONT_FAMILY = TYPOGRAPHY["family"]
POLL_SECONDS = 30
STALE_AFTER_SECONDS = 90
MAX_UI_LOG_LINES = 1200
APP_USER_MODEL_ID = "ICIT.Labboy.CoworkingBroadcast"
LOG_DIR = APP_DIR / "logs"
CONFIG_DIR = Path(os.environ.get("APPDATA", str(APP_DIR))) / "labboy-coworking-broadcast"
PREFERENCES_FILE = CONFIG_DIR / "preferences.json"
STARTUP_REGISTRY_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REGISTRY_VALUE = "LabboyCoworkingBroadcast"


def apply_theme_tokens(theme: str) -> str:
    """เลือกชุดสีให้วิดเจ็ตทั้งหมดใช้ tokens ของธีมเดียวกันตั้งแต่เริ่มหน้าต่าง"""
    global ACTIVE_THEME, COLORS, BG, WHITE, TEXT, MUTED, BLUE, BLUE_DARK, BLUE_PALE
    global GREEN, GREEN_SWITCH, GREEN_PALE, RED, RED_PALE, AMBER, AMBER_PALE
    global AMBER_BORDER, BORDER, INNER_BORDER, LOG_BG
    ACTIVE_THEME = theme if theme in DESIGN_TOKENS else "light"
    COLORS = DESIGN_TOKENS[ACTIVE_THEME]["colors"]
    BG = COLORS["window_bg"]
    WHITE = COLORS["surface"]
    TEXT = COLORS["text_primary"]
    MUTED = COLORS["text_secondary"]
    BLUE = COLORS["blue"]
    BLUE_DARK = COLORS["blue_dark"]
    BLUE_PALE = COLORS["blue_pale"]
    GREEN = COLORS["green"]
    GREEN_SWITCH = COLORS["green_switch"]
    GREEN_PALE = COLORS["green_pale"]
    RED = COLORS["red"]
    RED_PALE = COLORS["red_pale"]
    AMBER = COLORS["amber"]
    AMBER_PALE = COLORS["amber_pale"]
    AMBER_BORDER = COLORS["amber_border"]
    BORDER = COLORS["border"]
    INNER_BORDER = COLORS["inner_border"]
    LOG_BG = COLORS["log_bg"]
    return ACTIVE_THEME


def set_windows_app_identity() -> None:
    """ตั้งชื่อแอปให้ Windows ใช้ระบุตัวหน้าต่างบน taskbar"""
    if os.name != "nt":
        return
    try:
        shell32 = ctypes.windll.shell32
        shell32.SetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.c_wchar_p]
        shell32.SetCurrentProcessExplicitAppUserModelID.restype = ctypes.c_long
        shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


def load_preferences() -> dict[str, object]:
    """อ่านค่าหน้าต่างที่ไม่เป็นความลับจากโปรไฟล์ผู้ใช้ Windows"""
    try:
        value = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def windows_startup_enabled() -> bool:
    """ตรวจว่ามีรายการเริ่มโปรแกรมเมื่อผู้ใช้เข้าสู่ Windows หรือไม่"""
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY) as key:
            winreg.QueryValueEx(key, STARTUP_REGISTRY_VALUE)
        return True
    except (OSError, ImportError):
        return False


CREDENTIAL_TARGET = "labboy-coworking-broadcast/speaker-admin"


class _WinCredential(ctypes.Structure):
    class _FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FileTime),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_saved_speaker_password() -> str | None:
    """อ่านรหัสผ่านจาก Windows Credential Manager ของบัญชีผู้ใช้นี้"""
    if os.name != "nt":
        return None
    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    credential_ptr = ctypes.POINTER(_WinCredential)()
    advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                 ctypes.POINTER(ctypes.POINTER(_WinCredential))]
    advapi.CredReadW.restype = wintypes.BOOL
    advapi.CredFree.argtypes = [ctypes.c_void_p]
    advapi.CredFree.restype = None
    if not advapi.CredReadW(CREDENTIAL_TARGET, 1, 0, ctypes.byref(credential_ptr)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND: ยังไม่เคยบันทึกรหัส
            return None
        raise OSError(error, "อ่านรหัสผ่านจาก Windows Credential Manager ไม่สำเร็จ")
    try:
        credential = credential_ptr.contents
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-16-le")
    finally:
        advapi.CredFree(credential_ptr)


def save_speaker_password(password: str) -> None:
    """บันทึกรหัสผ่านแบบผูกกับบัญชี Windows ปัจจุบัน ไม่เก็บเป็นข้อความในโฟลเดอร์แอป"""
    if os.name != "nt":
        raise OSError("Windows Credential Manager ใช้ได้เฉพาะบน Windows")
    encoded = password.encode("utf-16-le")
    blob = ctypes.create_string_buffer(encoded)
    credential = _WinCredential()
    credential.Flags = 0
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = CREDENTIAL_TARGET
    credential.Comment = "labboy Coworking Broadcast speaker admin password"
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE: available to this Windows user
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = "admin"
    advapi = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi.CredWriteW.argtypes = [ctypes.POINTER(_WinCredential), wintypes.DWORD]
    advapi.CredWriteW.restype = wintypes.BOOL
    if not advapi.CredWriteW(ctypes.byref(credential), 0):
        error = ctypes.get_last_error()
        raise OSError(error, "บันทึกรหัสผ่านใน Windows Credential Manager ไม่สำเร็จ")


class BroadcastApp:
    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("labboy-coworking-broadcast")
        screen_w, screen_h = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        window_w = max(400, min(CONTROL_SIZES["window_width"], screen_w - 40))
        window_h = max(400, min(CONTROL_SIZES["window_height"], screen_h - 90))
        self.root.minsize(
            min(CONTROL_SIZES["min_window_width"], window_w),
            min(CONTROL_SIZES["min_window_height"], window_h),
        )
        self.root.geometry(f"{window_w}x{window_h}+{(screen_w-window_w)//2}+{(screen_h-window_h)//2}")
        self.root.configure(fg_color=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.root.bind("<Unmap>", self.on_window_minimize)
        self.preferences = load_preferences()
        self.schedule_url = tk.StringVar(
            value=str(self.preferences.get("schedule_url", DEFAULT_SCHEDULE_URL))
        )
        saved_startup = self.preferences.get("startup_enabled")
        initial_startup = bool(saved_startup) if isinstance(saved_startup, bool) else windows_startup_enabled()
        self.startup_enabled = tk.BooleanVar(value=initial_startup)
        self.close_to_tray = tk.BooleanVar(value=bool(self.preferences.get("close_to_tray", False)))
        selected_theme = str(self.preferences.get("appearance", ACTIVE_THEME))
        self.appearance_choice = tk.StringVar(value=THEME_LABELS.get(selected_theme, THEME_LABELS["light"]))
        try:
            self.saved_speaker_password = read_saved_speaker_password()
            self.credential_store_error = ""
        except (OSError, AttributeError) as exc:
            self.saved_speaker_password = None
            self.credential_store_error = str(exc)
        self.tray_icon = None
        self.tray_thread_started = False
        self.win32_icon_handles: list[int] = []
        if ICON_PATH.is_file():
            try:
                # สำรองการตั้งไอคอนผ่าน Tk เผื่อ Windows API ใช้ไม่ได้
                self.root.iconbitmap(default=str(ICON_PATH))
            except tk.TclError:
                pass
        global FONT_FAMILY
        self.private_fonts: list[Path] = []
        if os.name == "nt":
            try:
                gdi = ctypes.windll.gdi32
                gdi.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
                gdi.AddFontResourceExW.restype = ctypes.c_int
                for font_path in sorted((RESOURCE_DIR / "fonts").glob("IBMPlexSansThai-*.ttf")):
                    # โหลดฟอนต์เฉพาะโปรแกรมนี้ ไม่เปลี่ยนค่าฟอนต์ของ Windows ทั้งระบบ
                    if gdi.AddFontResourceExW(str(font_path), 0x10, None):
                        self.private_fonts.append(font_path)
            except (AttributeError, OSError):
                pass
        available_fonts = {name.casefold() for name in tkfont.families(root)}
        FONT_FAMILY = (
            TYPOGRAPHY["family"]
            if TYPOGRAPHY["family"].casefold() in available_fonts
            else TYPOGRAPHY["fallback"]
        )

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.sleep_prevention_active = False
        self.stopping = False
        self.mode = tk.StringVar(value="ใช้งานจริง")
        self.mode_toggle_enabled = True
        self.password = tk.StringVar()
        self.show_password = tk.BooleanVar(value=False)
        self.credential_dialog: ctk.CTkToplevel | None = None
        self.pending_credential_open = False
        self.credential_restart_pending = False
        self.pending_test_room: str | None = None
        self.pending_test_resume = False
        self.resume_monitor_after_test = False
        self.has_started_monitor = False
        self.last_check = tk.StringVar(value="ยังไม่เคยอ่าน K-Room")
        self.next_sound_text = tk.StringVar(value="เริ่มระบบเพื่อคำนวณรอบถัดไป")
        self.next_sound_eta = tk.StringVar(value="รอข้อมูลตาราง")
        self.clock_date = tk.StringVar()
        self.clock_time = tk.StringVar()
        self.status_text = tk.StringVar(value="ระบบ: ยังไม่เริ่มตรวจ")
        self.audio_status_text = tk.StringVar(value="เสียงล่าสุด: ยังไม่มีผล")
        self.active_mode_label = ""
        self.monitor_started_at: datetime | None = None
        self.last_successful_read: datetime | None = None
        self.next_poll_at: datetime | None = None
        self.monitor_error = False
        self.speaker_auth_error = False
        self.last_read_empty = False
        self.session_started_at: datetime | None = None
        self.session_finished_at: datetime | None = None
        self.session_read_count = 0
        self.session_booking_count = 0
        self.session_speaker_successes = 0
        self.session_speaker_failures = 0
        self.is_monitor_session = False
        self.booking_records: list[dict[str, object]] = []
        self.observed_in_use_keys: set[str] = set()
        self.booking_alerts: dict[str, str] = {}
        self.booking_alert_colors: dict[str, str] = {}
        self.schedule_render_job: str | None = None
        self.notified_alerts: set[str] = set()
        self.pending_alerts: dict[str, tuple[str, str]] = {}
        self.active_alert_key: str | None = None
        self.schedule_room_filter = tk.StringVar(value="ทุกห้อง")
        self.schedule_status_filter = tk.StringVar(value="ทุกสถานะ")
        self.schedule_sort = tk.StringVar(value="ใกล้หมดเวลาก่อน")
        self.room_status: dict[str, ctk.CTkLabel] = {}
        self.room_test_buttons: dict[str, ctk.CTkButton] = {}
        self.schedule_rows: list[dict[str, object]] = []
        self._last_bookings_signature: tuple[object, ...] | None = None
        self._last_logs_signature: tuple[tuple[str, ...], ...] | None = None
        self.activity_events: list[dict[str, str]] = []
        self.activity_rows: list[dict[str, object]] = []
        self.seen_booking_event_keys: set[str] = set()

        self.logo_image: ctk.CTkImage | None = None
        self.header_logo_image: ctk.CTkImage | None = None
        self.tk_logo_image: tk.PhotoImage | None = None
        if LOGO_PATH.is_file():
            logo = Image.open(LOGO_PATH).convert("RGBA")
            self.logo_image = ctk.CTkImage(light_image=logo, dark_image=logo, size=(48, 48))
            self.header_logo_image = ctk.CTkImage(light_image=logo, dark_image=logo, size=(48, 48))
            try:
                self.tk_logo_image = tk.PhotoImage(file=str(LOGO_PATH))
                self.root.iconphoto(True, self.tk_logo_image)
            except tk.TclError:
                pass

        self.build_ui()
        self.bind_accessible_shortcuts()
        self.install_focus_indicators()
        self.refresh_primary_action_label()
        # บังคับตั้งไอคอน native ของ Windows หลังหน้าต่างมี HWND แล้ว
        self.root.update_idletasks()
        self.apply_windows_icon()
        self.root.report_callback_exception = self.report_callback_exception
        self.update_clock()
        self.root.after(150, self.process_events)
        if os.name == "nt" and self.startup_enabled.get():
            try:
                self.write_startup_registration(True)
                self.save_preferences(show_error=False)
            except (OSError, ImportError) as exc:
                self.startup_enabled.set(False)
                self.show_app_dialog("ตั้งค่าเริ่มพร้อม Windows ไม่สำเร็จ", str(exc), kind="warning")
        if bool(getattr(sys, "_labboy_start_tray", False)) and self.close_to_tray.get():
            self.root.after(250, self.hide_to_tray)
        self.root.after(650, self.auto_start_live)

    def apply_windows_icon(self) -> None:
        """กำหนดไอคอน small/large ให้ HWND เพื่อให้ title bar และ taskbar ใช้ไฟล์ ICO"""
        if os.name != "nt" or not ICON_PATH.is_file():
            return
        try:
            user32 = ctypes.windll.user32
            user32.LoadImageW.argtypes = [
                wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            ]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [
                wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            ]
            user32.SendMessageW.restype = wintypes.LPARAM
            # IMAGE_ICON + LR_LOADFROMFILE + LR_DEFAULTSIZE
            icon_handle = user32.LoadImageW(None, str(ICON_PATH), 1, 0, 0, 0x50)
            if not icon_handle:
                return
            handle_value = int(icon_handle)
            hwnd = self.root.winfo_id()
            # WM_SETICON: ICON_SMALL=0 และ ICON_BIG=1
            user32.SendMessageW(hwnd, 0x0080, 0, handle_value)
            user32.SendMessageW(hwnd, 0x0080, 1, handle_value)
            self.win32_icon_handles.append(handle_value)
        except (AttributeError, OSError, TypeError, ValueError):
            # iconbitmap/iconphoto ที่ตั้งไว้ก่อนหน้านี้ยังทำหน้าที่เป็น fallback
            pass

    def build_ui(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.shell = ctk.CTkFrame(self.root, fg_color=BG, corner_radius=CORNER_RADII["none"])
        self.shell.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.shell.grid_rowconfigure(0, weight=0)
        self.shell.grid_rowconfigure(1, weight=1)
        self.shell.grid_columnconfigure(0, weight=0, minsize=286)
        self.shell.grid_columnconfigure(1, weight=1, minsize=760)

        self.build_navbar()

        self.sidebar = ctk.CTkFrame(self.shell, fg_color=COLORS["log_bg"], corner_radius=CORNER_RADII["none"])
        self.sidebar.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(2, weight=1)

        self.content_host = ctk.CTkFrame(self.shell, fg_color="transparent", corner_radius=CORNER_RADII["none"])
        self.content_host.grid(row=1, column=1, sticky="nsew")
        self.content_host.grid_rowconfigure(0, weight=1)
        self.content_host.grid_columnconfigure(0, weight=1)

        self.page = ctk.CTkFrame(self.content_host, fg_color="transparent", corner_radius=CORNER_RADII["none"])
        self.page.grid(row=0, column=0, sticky="nsew")
        self.page.grid_columnconfigure(0, weight=1)
        self.page.grid_rowconfigure(1, weight=1)
        self.settings_page = ctk.CTkFrame(self.content_host, fg_color="transparent", corner_radius=CORNER_RADII["none"])
        self.settings_page.grid(row=0, column=0, sticky="nsew")
        self.settings_page.grid_columnconfigure(0, weight=1)
        self.settings_page.grid_remove()

        self.build_controls()
        self.build_rooms()
        self.build_details()
        self.build_footer()

    def show_settings(self) -> None:
        self.page.grid_remove()
        self.settings_page.grid()
        self.settings_nav_button.configure(text="กลับหน้าหลัก", command=self.show_dashboard)

    def show_dashboard(self) -> None:
        self.settings_page.grid_remove()
        self.page.grid()
        self.settings_nav_button.configure(text="ตั้งค่า", command=self.show_settings)

    def bind_accessible_shortcuts(self) -> None:
        self.root.bind_all("<F8>", self._shortcut_toggle_monitor, add="+")
        for number, room in enumerate(ROOMS, start=1):
            self.root.bind_all(
                f"<Control-Key-{number}>",
                lambda _event, selected=room: self._shortcut_test_room(selected),
                add="+",
            )
        self.add_tooltip(self.start_button, "F8 · เริ่ม หยุดชั่วคราว หรือทำงานต่อ")
        for number, room in enumerate(ROOMS, start=1):
            self.add_tooltip(self.room_test_buttons[room], f"Ctrl+{number} · ทดสอบเสียงห้อง {room} (มีคำยืนยัน)")

    def _shortcut_allowed(self) -> bool:
        if self.root.grab_current() not in (None, self.root):
            return False
        focus = self.root.focus_get()
        return focus is None or focus.winfo_class() != "Entry"

    def _shortcut_toggle_monitor(self, _event: object = None) -> str:
        if self._shortcut_allowed():
            self.primary_action()
        return "break"

    def _shortcut_test_room(self, room: str) -> str:
        if self._shortcut_allowed() and self.room_test_buttons[room].cget("state") != "disabled":
            self.test_speaker(room)
        return "break"

    @staticmethod
    def add_tooltip(widget: tk.Widget, message: str | Callable[[], str]) -> None:
        state: dict[str, object] = {"timer": None, "window": None}

        def hide(_event: object = None) -> None:
            timer = state.get("timer")
            if timer is not None:
                try:
                    widget.after_cancel(timer)
                except tk.TclError:
                    pass
                state["timer"] = None
            window = state.get("window")
            if window is not None:
                try:
                    window.destroy()
                except tk.TclError:
                    pass
                state["window"] = None

        def show() -> None:
            if not widget.winfo_exists():
                return
            window = tk.Toplevel(widget.winfo_toplevel())
            state["window"] = window
            window.overrideredirect(True)
            window.configure(bg=COLORS["text_primary"])
            full_message = message() if callable(message) else str(message)
            label = tk.Label(window, text=full_message, bg=COLORS["text_primary"],
                fg=COLORS["white_text"], font=(FONT_FAMILY, FONT_SIZES["secondary"]),
                padx=9, pady=5)
            label.pack()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 5
            window.geometry(f"+{x}+{y}")

        def schedule(_event: object = None) -> None:
            hide()
            state["timer"] = widget.after(650, show)

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    def install_focus_indicators(self) -> None:
        widgets: list[tk.Widget] = [
            self.mode_switch, self.start_button, self.credential_button,
            self.settings_nav_button, self.startup_check, self.tray_check,
            self.appearance_picker, self.room_filter, self.status_filter, self.sort_picker,
            *self.room_test_buttons.values(), *self.room_detail_buttons.values(),
            self.activity_clear_button, self.activity_open_log_button,
        ]
        for widget in widgets:
            if isinstance(widget, ctk.CTkOptionMenu):
                original_fg = widget.cget("fg_color")
                original_button = widget.cget("button_color")

                def menu_focused(_event: object, item=widget) -> None:
                    item.configure(fg_color=BLUE_PALE, button_color=BLUE)

                def menu_blurred(_event: object, item=widget, fg=original_fg, button=original_button) -> None:
                    item.configure(fg_color=fg, button_color=button)

                widget.bind("<FocusIn>", menu_focused, add="+")
                widget.bind("<FocusOut>", menu_blurred, add="+")
                continue
            try:
                original_color = widget.cget("border_color")
                original_width = widget.cget("border_width")
            except (tk.TclError, KeyError, AttributeError, ValueError):
                continue

            def focused(_event: object, item=widget) -> None:
                try:
                    item.configure(border_color=BLUE, border_width=2)
                except (tk.TclError, TypeError, AttributeError, ValueError):
                    pass

            def blurred(_event: object, item=widget, color=original_color, width=original_width) -> None:
                try:
                    item.configure(border_color=color, border_width=width)
                except (tk.TclError, TypeError, AttributeError, ValueError):
                    pass

            widget.bind("<FocusIn>", focused, add="+")
            widget.bind("<FocusOut>", blurred, add="+")

    def build_navbar(self) -> None:
        nav = ctk.CTkFrame(self.shell, fg_color=COLORS["log_bg"], corner_radius=CORNER_RADII["none"])
        self.navbar = nav
        nav.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        nav.grid_columnconfigure(1, weight=1)
        nav.grid_columnconfigure(3, weight=0)
        nav.grid_columnconfigure(4, weight=0)
        ctk.CTkLabel(
            nav, text="", image=self.header_logo_image,
            width=40, height=40,
            fg_color="transparent",
        ).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=7)
        ctk.CTkLabel(
            nav, text="ระบบประกาศเสียงห้องติว", text_color=TEXT,
            font=(FONT_FAMILY, 24, "bold"), anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=(0, 12))
        time_pill = ctk.CTkFrame(
            nav, fg_color=WHITE, corner_radius=CORNER_RADII["pill"],
            border_width=CONTROL_SIZES["border_width"], border_color=COLORS["card_border"],
        )
        self.time_pill = time_pill
        time_pill.grid(row=0, column=5, sticky="e", padx=(8, 12), pady=7)
        ctk.CTkLabel(
            time_pill, textvariable=self.clock_date, text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["body"]),
        ).pack(side="left", padx=(14, 7), pady=10)
        ctk.CTkFrame(time_pill, width=CONTROL_SIZES["separator_width"], height=CONTROL_SIZES["separator_height"], fg_color=BORDER).pack(side="left")
        ctk.CTkLabel(
            time_pill, textvariable=self.clock_time, text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["metric"], "bold"),
        ).pack(side="left", padx=(8, 14), pady=10)

    def build_hero(self) -> None:
        """คงชื่อเมธอดไว้สำหรับความเข้ากันได้; header ปัจจุบันรวมข้อมูลส่วนนี้แล้ว"""
        return

    def build_controls(self) -> None:
        top = self.navbar
        top.grid_columnconfigure(2, weight=0)
        top.grid_columnconfigure(3, weight=1)
        self.mode_hint = tk.StringVar(value="ประกาศเสียงตามกำหนดการอัตโนมัติ")
        mode_group = ctk.CTkFrame(top, fg_color="transparent")
        mode_group.grid(row=0, column=2, sticky="w", padx=(5, 8), pady=5)
        self.mode_switch = ctk.CTkSwitch(
            mode_group, text="โหมดใช้งานจริง", variable=self.mode,
            onvalue="ใช้งานจริง", offvalue="ทดลอง", command=self.toggle_mode,
            progress_color=GREEN_SWITCH, button_color=WHITE,
            button_hover_color=COLORS["window_bg"], fg_color=COLORS["switch_track_off"],
            text_color=COLORS["text_primary"], text_color_disabled=COLORS["text_primary"],
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"),
            switch_width=CONTROL_SIZES["switch_width"], switch_height=CONTROL_SIZES["switch_height"],
        )
        self.mode_switch.grid(row=0, column=0, sticky="w")

        status = ctk.CTkFrame(top, fg_color=GREEN_PALE, corner_radius=CORNER_RADII["pill"])
        self.status_pill = status
        status.grid(row=0, column=3, sticky="w", padx=(3, 6), pady=5)
        status.grid_columnconfigure(1, weight=1)
        self.status_dot = ctk.CTkLabel(status, text="●", text_color=GREEN,
            width=CONTROL_SIZES["status_dot_width"], font=(FONT_FAMILY, FONT_SIZES["caption"], "bold"))
        self.status_dot.grid(row=0, column=0, sticky="w", padx=(10, 3), pady=8)
        self.status_label = ctk.CTkLabel(status, textvariable=self.status_text, text_color=GREEN,
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"), anchor="w")
        self.status_label.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=8)
        # เก็บ widget/ตัวแปรเดิมไว้รองรับการอัปเดตจาก monitor แต่ซ่อนข้อความสถานะซ้ำบนหน้าหลัก
        self.audio_status_label = ctk.CTkLabel(status, textvariable=self.audio_status_text,
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]))
        self.audio_status_label.grid_remove()
        self.last_check_label = ctk.CTkLabel(top, textvariable=self.last_check, text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"]))
        self.last_check_label.grid_remove()

        buttons = ctk.CTkFrame(top, fg_color="transparent")
        buttons.grid(row=0, column=4, sticky="e", padx=(0, 4), pady=5)
        self.start_button = ctk.CTkButton(
            buttons, text="ทำงานต่อ", command=self.primary_action,
            fg_color=AMBER_PALE, hover_color=COLORS["hover_warning"], text_color=AMBER,
            border_width=CONTROL_SIZES["border_width"], border_color=AMBER_BORDER,
            corner_radius=CORNER_RADII["control"], height=CONTROL_SIZES["main_button_height"],
            width=118, font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"),
        )
        self.start_button.pack(side="left")

        self.notice_area = ctk.CTkFrame(self.page, fg_color="transparent", corner_radius=CORNER_RADII["none"])
        self.notice_area.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.notice_area.grid_columnconfigure(0, weight=1)
        self.alert_banner = ctk.CTkFrame(self.notice_area, fg_color=COLORS["red_pale"],
            corner_radius=CORNER_RADII["metric"], border_width=CONTROL_SIZES["border_width"], border_color=RED)
        self.alert_banner.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.alert_banner.grid_columnconfigure(1, weight=1)
        self.alert_title_label = ctk.CTkLabel(self.alert_banner, text="", text_color=RED,
            font=(FONT_FAMILY, FONT_SIZES["lead"], "bold"), anchor="w")
        self.alert_title_label.grid(row=0, column=0, sticky="w", padx=(12, 8), pady=(7, 0))
        self.alert_message_label = ctk.CTkLabel(self.alert_banner, text="", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w", justify="left")
        self.alert_message_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        self.alert_action_button = ctk.CTkButton(self.alert_banner, text="เปิดบันทึก", command=self.open_log_folder,
            fg_color=RED, hover_color=COLORS["blue_dark"], text_color=WHITE,
            height=CONTROL_SIZES["compact_button_height"], font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"))
        self.alert_action_button.grid(row=0, column=1, sticky="e", padx=(8, 42), pady=(6, 2))
        self.alert_close_button = ctk.CTkButton(self.alert_banner, text="ปิด", command=self.dismiss_important_alert,
            fg_color="transparent", hover_color=COLORS["red_pale"], text_color=RED, width=42,
            height=CONTROL_SIZES["compact_button_height"], font=(FONT_FAMILY, FONT_SIZES["secondary"]))
        self.alert_close_button.grid(row=0, column=2, rowspan=2, sticky="e", padx=(0, 8), pady=6)
        self.alert_banner.grid_remove()

        banner = ctk.CTkFrame(self.notice_area, fg_color="transparent", corner_radius=CORNER_RADII["none"])
        banner.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        banner.grid_columnconfigure(2, weight=1)
        bell_icon = self.create_line_icon(banner, "bell", BG, BLUE, 22)
        bell_icon.grid(row=0, column=0, rowspan=2, padx=(2, 0), pady=2)
        ctk.CTkLabel(banner, text="เสียงรอบถัดไป", text_color=BLUE,
            font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"), anchor="w").grid(
                row=0, column=1, sticky="sw", padx=(3, 9), pady=(7, 0))
        self.next_sound_label = ctk.CTkLabel(banner, textvariable=self.next_sound_text, text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"), anchor="w")
        self.next_sound_label.grid(row=0, column=2, rowspan=2, sticky="w", pady=6)
        ctk.CTkLabel(banner, textvariable=self.next_sound_eta, text_color=BLUE,
            font=(FONT_FAMILY, FONT_SIZES["body"]), anchor="e").grid(row=0, column=3, rowspan=2, sticky="e", padx=14)

        # ตัวเลขรอบปัจจุบันยังคำนวณไว้เพื่อความเข้ากันได้ แต่ไม่แสดงซ้ำบนแดชบอร์ด
        self.session_summary_vars = {
            "duration": tk.StringVar(value="ยังไม่เริ่ม"),
            "reads": tk.StringVar(value="0 รอบ"),
            "bookings": tk.StringVar(value="0 รายการ"),
            "audio": tk.StringVar(value="0 สำเร็จ · 0 ไม่สำเร็จ"),
        }
        self.audio_metric_value = ctk.CTkLabel(self.notice_area, textvariable=self.session_summary_vars["audio"])
        self.refresh_session_summary()
        self.select_mode()

    def build_rooms(self) -> None:
        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(16, 10))
        brand.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(brand, text="ลำโพงประจำห้อง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(row=0, column=0, sticky="sw")
        ctk.CTkLabel(brand, text="สถานะจากการทดสอบและการส่งเสียงล่าสุด", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").grid(row=1, column=0, sticky="nw")
        ctk.CTkLabel(self.sidebar, text="สถานะอุปกรณ์", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"), anchor="w").grid(
                row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
        room_grid = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent",
            corner_radius=CORNER_RADII["none"], scrollbar_button_color=COLORS["scrollbar"])
        self.set_scrollbar_width(room_grid, 10)
        room_grid.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        room_grid.grid_columnconfigure(0, weight=1)
        self.room_ip_labels: dict[str, ctk.CTkLabel] = {}
        self.room_detail_frames: dict[str, ctk.CTkFrame] = {}
        self.room_detail_buttons: dict[str, ctk.CTkButton] = {}
        room_tints = {
            "Windows": (COLORS["room_windows_bg"], BLUE),
            "iOS": (COLORS["room_ios_bg"], COLORS["room_ios_text"]),
            "Android": (COLORS["green_pale"], GREEN),
            "Linux": (COLORS["room_linux_bg"], AMBER),
        }
        for row_index, (room, device) in enumerate(ROOMS.items()):
            card = self.panel(room_grid, corner=16)
            card.grid(row=row_index, column=0, sticky="ew", padx=2, pady=(0, 7))
            card.grid_columnconfigure(0, weight=1)
            name_line = ctk.CTkFrame(card, fg_color="transparent")
            name_line.grid(row=0, column=0, sticky="ew", padx=9, pady=(7, 2))
            name_line.grid_columnconfigure(1, weight=1)
            tint, icon_color = room_tints[room]
            icon = ctk.CTkFrame(name_line, width=32, height=32, fg_color=tint, corner_radius=CORNER_RADII["room_icon"])
            icon.grid(row=0, column=0, sticky="w", padx=(0, 7))
            icon.grid_propagate(False)
            self.create_line_icon(icon, "speaker", tint, icon_color, 24).place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(name_line, text=room, text_color=TEXT,
                         font=(FONT_FAMILY, FONT_SIZES["room"], "bold"), anchor="w").grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(name_line, text=f"ROOM {device['number']}",
                         text_color=MUTED, fg_color=LOG_BG, corner_radius=CORNER_RADII["room_badge"],
                         font=(FONT_FAMILY, FONT_SIZES["caption"], "bold"), padx=7, pady=3).grid(
                             row=0, column=2, sticky="e")
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=1, column=0, sticky="ew", padx=9, pady=(0, 3))
            info.grid_columnconfigure(0, weight=1)
            state = ctk.CTkLabel(
                info, text="● ยังไม่มีผลทดสอบ", text_color=MUTED,
                font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w",
            )
            state.grid(row=0, column=0, sticky="w")
            self.room_status[room] = state
            actions = ctk.CTkFrame(card, fg_color="transparent")
            actions.grid(row=2, column=0, sticky="ew", padx=9, pady=(0, 6))
            actions.grid_columnconfigure(0, weight=1)
            test_button = ctk.CTkButton(
                actions, text="ทดสอบเสียง 1 ครั้ง",
                command=lambda selected=room: self.test_speaker(selected),
                fg_color=WHITE, hover_color=BLUE_PALE, text_color=BLUE,
                text_color_disabled=MUTED, border_width=CONTROL_SIZES["border_width"],
                border_color=COLORS["control_border"], corner_radius=CORNER_RADII["small_control"],
                height=CONTROL_SIZES["compact_button_height"], width=150,
                font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"),
            )
            test_button.grid(row=0, column=0, sticky="w")
            self.room_test_buttons[room] = test_button
            detail_button = ctk.CTkButton(actions, text="รายละเอียด", command=lambda selected=room: self.toggle_room_details(selected),
                fg_color="transparent", hover_color=LOG_BG, text_color=MUTED,
                height=CONTROL_SIZES["compact_button_height"], width=80,
                font=(FONT_FAMILY, FONT_SIZES["secondary"]))
            detail_button.grid(row=0, column=1, sticky="e", padx=(5, 0))
            self.room_detail_buttons[room] = detail_button
            detail = ctk.CTkFrame(card, fg_color=LOG_BG, corner_radius=CORNER_RADII["timeline_row"])
            detail.grid(row=3, column=0, sticky="ew", padx=9, pady=(0, 8))
            ip_label = ctk.CTkLabel(detail, text=f"IP  {device['ip']}", text_color=MUTED,
                font=(TYPOGRAPHY["mono_family"], FONT_SIZES["secondary"]), anchor="w")
            ip_label.pack(anchor="w", padx=8, pady=5)
            detail.grid_remove()
            self.room_ip_labels[room] = ip_label
            self.room_detail_frames[room] = detail

    def toggle_room_details(self, room: str) -> None:
        frame = self.room_detail_frames[room]
        if frame.winfo_manager():
            frame.grid_remove()
            self.room_detail_buttons[room].configure(text="รายละเอียด")
        else:
            frame.grid()
            self.room_detail_buttons[room].configure(text="ซ่อนรายละเอียด")

    def build_details(self) -> None:
        details = ctk.CTkFrame(self.page, fg_color="transparent")
        details.grid(row=1, column=0, sticky="nsew", pady=(0, 0))
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(0, weight=3)
        details.grid_rowconfigure(1, weight=2)

        schedule_card = self.panel(details)
        schedule_card.grid(row=0, column=0, sticky="nsew", pady=(0, 7))
        schedule_card.grid_columnconfigure(0, weight=1)
        schedule_card.grid_rowconfigure(2, weight=1)
        schedule_header = ctk.CTkFrame(schedule_card, fg_color="transparent")
        schedule_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 6))
        schedule_header.grid_columnconfigure(0, weight=1)
        title_group = ctk.CTkFrame(schedule_header, fg_color="transparent")
        title_group.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(title_group, text="รายการจองวันนี้", text_color=TEXT,
                     font=(FONT_FAMILY, FONT_SIZES["control"], "bold")).pack(side="left")
        self.booking_date_label = tk.StringVar(value="")
        ctk.CTkLabel(title_group, textvariable=self.booking_date_label,
                     text_color=COLORS["text_muted"], font=(FONT_FAMILY, FONT_SIZES["secondary"])).pack(side="left", padx=(10, 0))
        filters = ctk.CTkFrame(schedule_header, fg_color="transparent")
        filters.grid(row=0, column=1, sticky="e")
        option_style = {
            "fg_color": LOG_BG, "button_color": COLORS["button_neutral"],
            "button_hover_color": COLORS["hover_neutral"], "text_color": TEXT,
            "dropdown_fg_color": WHITE, "dropdown_text_color": TEXT,
            "dropdown_hover_color": BLUE_PALE, "corner_radius": CORNER_RADII["filter"],
            "height": CONTROL_SIZES["filter_height"], "font": (FONT_FAMILY, FONT_SIZES["secondary"]),
            "dropdown_font": (FONT_FAMILY, FONT_SIZES["secondary"]),
        }
        ctk.CTkLabel(filters, text="ห้อง", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold")).pack(side="left", padx=(0, 4))
        self.room_filter = ctk.CTkOptionMenu(
            filters, variable=self.schedule_room_filter,
            values=["ทุกห้อง", *ROOMS.keys()], width=CONTROL_SIZES["room_filter_width"],
            command=lambda _value: self.render_schedule_rows(), **option_style,
        )
        self.room_filter.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(filters, text="สถานะ", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold")).pack(side="left", padx=(0, 4))
        self.status_filter = ctk.CTkOptionMenu(
            filters, variable=self.schedule_status_filter,
            values=["ทุกสถานะ", "จองแล้ว", "ระงับการจอง", "ครบเวลาแล้ว", "กำลังใช้ห้อง", "เช็คอินแล้ว", "ไม่ทราบสถานะ"],
            width=CONTROL_SIZES["status_filter_width"], command=lambda _value: self.render_schedule_rows(), **option_style,
        )
        self.status_filter.pack(side="left", padx=(0, 5))
        ctk.CTkLabel(filters, text="เรียง", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold")).pack(side="left", padx=(0, 4))
        self.sort_picker = ctk.CTkOptionMenu(
            filters, variable=self.schedule_sort,
            values=["ใกล้หมดเวลาก่อน", "เวลาเริ่มก่อน"], width=CONTROL_SIZES["sort_filter_width"],
            command=lambda _value: self.render_schedule_rows(), **option_style,
        )
        self.sort_picker.pack(side="left")
        labels = ctk.CTkFrame(schedule_card, fg_color=LOG_BG, corner_radius=CORNER_RADII["table_header"], height=CONTROL_SIZES["table_header_height"])
        labels.grid(row=1, column=0, sticky="ew", padx=12, pady=(4, 2))
        labels.grid_propagate(False)
        for col, (text, weight) in enumerate((("ห้อง", 3), ("ช่วงเวลา", 2), ("สถานะ", 2), ("การแจ้งเตือน", 3))):
            labels.grid_columnconfigure(col, weight=weight, uniform="schedule-cols")
            ctk.CTkLabel(labels, text=text, text_color=MUTED,
                         font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"), anchor="w").grid(
                             row=0, column=col, sticky="ew", padx=(8, 2), pady=(4, 2))
        self.schedule_list = ctk.CTkScrollableFrame(
            schedule_card, fg_color="transparent", corner_radius=CORNER_RADII["none"],
            scrollbar_button_color=COLORS["scrollbar"],
        )
        self.set_scrollbar_width(self.schedule_list, 10)
        self.schedule_list.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.schedule_list.grid_columnconfigure(0, weight=1)
        self.empty_schedule = ctk.CTkLabel(
            self.schedule_list, text="ยังไม่มีข้อมูล · ระบบจะอ่านรายการจองวันนี้ให้อัตโนมัติ",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["body"]),
        )
        self.empty_schedule.grid(row=0, column=0, sticky="ew", pady=30)

        log_card = self.panel(details)
        log_card.grid(row=1, column=0, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        header_title = ctk.CTkFrame(log_header, fg_color="transparent")
        header_title.pack(side="left")
        ctk.CTkLabel(header_title, text="กิจกรรมล่าสุด", text_color=TEXT,
                     font=(FONT_FAMILY, FONT_SIZES["control"], "bold")).pack(anchor="w")
        self.activity_summary_text = tk.StringVar(value="อัปเดตแบบเรียลไทม์ · ผลการประกาศรอบนี้: 0 สำเร็จ · 0 ไม่สำเร็จ")
        ctk.CTkLabel(header_title, textvariable=self.activity_summary_text,
                     text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"])).pack(anchor="w")
        self.activity_open_log_button = ctk.CTkButton(
            log_header, text="เปิดโฟลเดอร์ Log", command=self.open_log_folder,
            fg_color="transparent", hover_color=BLUE_PALE, text_color=BLUE,
            corner_radius=CORNER_RADII["timeline_row"], width=CONTROL_SIZES["open_log_button_width"], height=CONTROL_SIZES["toolbar_button_height"], font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"),
        )
        self.activity_open_log_button.pack(side="right", padx=(6, 0))
        self.activity_clear_button = ctk.CTkButton(
            log_header, text="ล้าง", command=self.clear_logs,
            fg_color="transparent", hover_color=BLUE_PALE, text_color=BLUE,
            corner_radius=CORNER_RADII["timeline_row"], width=CONTROL_SIZES["clear_log_button_width"], height=CONTROL_SIZES["toolbar_button_height"], font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.activity_clear_button.pack(side="right")
        self.activity_list = ctk.CTkScrollableFrame(
            log_card, fg_color=LOG_BG, corner_radius=CORNER_RADII["timeline_panel"],
            scrollbar_button_color=COLORS["scrollbar"],
        )
        self.set_scrollbar_width(self.activity_list, 10)
        self.activity_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.activity_list.grid_columnconfigure(0, weight=1)
        self.activity_empty = ctk.CTkLabel(
            self.activity_list, text="กิจกรรมจากระบบจะแสดงที่นี่",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.activity_empty.grid(row=0, column=0, sticky="ew", pady=24)
        for _ in range(10):
            row = ctk.CTkFrame(self.activity_list, fg_color="transparent", corner_radius=CORNER_RADII["timeline_row"])
            row.grid_columnconfigure(1, weight=1)
            dot = ctk.CTkLabel(row, text="●", width=CONTROL_SIZES["timeline_dot_width"], text_color=GREEN_SWITCH,
                               font=(FONT_FAMILY, FONT_SIZES["body"], "bold"))
            dot.grid(row=0, column=0, rowspan=2, sticky="n", padx=(5, 6), pady=(5, 0))
            title = ctk.CTkLabel(row, text="", text_color=COLORS["text_primary"],
                                 font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"), anchor="w", wraplength=0)
            title.grid(row=0, column=1, sticky="ew", pady=(4, 0))
            subtitle = ctk.CTkLabel(row, text="", text_color=COLORS["text_secondary"],
                                    font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w", wraplength=0)
            subtitle.grid(row=1, column=1, sticky="ew", pady=(0, 4))
            timestamp = ctk.CTkLabel(row, text="", text_color=COLORS["text_muted"], width=CONTROL_SIZES["timestamp_width"],
                                     font=(FONT_FAMILY, FONT_SIZES["caption"]), anchor="e")
            timestamp.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(6, 8), pady=(5, 0))
            self.activity_rows.append({"frame": row, "dot": dot, "title": title,
                                       "subtitle": subtitle, "time": timestamp})
            row.grid_remove()

    def build_footer(self) -> None:
        ctk.CTkLabel(self.settings_page, text="ตั้งค่า", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["title"], "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(18, 14))
        credentials = self.panel(self.settings_page)
        credentials.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 10))
        credentials.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(credentials, text="รหัสลำโพง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        saved_label = "บันทึกใน Windows แล้ว" if self.saved_speaker_password else "ยังไม่ได้บันทึกรหัสผ่าน"
        self.credential_status_label = ctk.CTkLabel(credentials, text=saved_label,
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w")
        self.credential_status_label.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        self.credential_button = ctk.CTkButton(
            credentials, text="จัดการรหัสลำโพง", command=self.open_credential_dialog,
            fg_color=COLORS["surface"], hover_color=COLORS["log_bg"], text_color=COLORS["text_dark"],
            text_color_disabled=COLORS["text_muted"], border_width=CONTROL_SIZES["border_width"],
            border_color=COLORS["control_border"], corner_radius=CORNER_RADII["control"],
            height=CONTROL_SIZES["main_button_height"], width=CONTROL_SIZES["credential_button_width"],
            font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"),
        )
        self.credential_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=16, pady=12)

        source = self.panel(self.settings_page)
        source.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 10))
        source.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(source, text="แหล่งตารางจอง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(
                row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(source, text="URL ของหน้า K-Room ที่โปรแกรมใช้เปิดอ่านตาราง",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").grid(
                row=1, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))
        self.schedule_url_entry = ctk.CTkEntry(
            source, textvariable=self.schedule_url, height=CONTROL_SIZES["main_button_height"],
            font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.schedule_url_entry.grid(row=2, column=0, sticky="ew", padx=(16, 8), pady=(0, 14))
        ctk.CTkButton(
            source, text="บันทึก URL", command=self.save_schedule_url,
            fg_color=COLORS["blue_action"], hover_color=COLORS["blue_action_hover"],
            text_color=COLORS["white_text"], height=CONTROL_SIZES["main_button_height"],
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"),
        ).grid(row=2, column=1, sticky="e", padx=(0, 16), pady=(0, 14))

        devices = self.panel(self.settings_page)
        devices.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 10))
        devices.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(devices, text="อุปกรณ์และห้อง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(devices,
            text=f"ไฟล์ตั้งค่าชื่อห้อง, หมายเลขห้อง, IP และ Audio ID อยู่ที่ {ROOM_CONFIG_PATH}",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w",
            wraplength=760, justify="left").grid(
                row=1, column=0, sticky="w", padx=16, pady=(0, 12))
        ctk.CTkButton(
            devices, text="เปิดไฟล์ตั้งค่าอุปกรณ์", command=self.open_room_config,
            fg_color=COLORS["surface"], hover_color=COLORS["log_bg"],
            text_color=COLORS["text_dark"], border_width=CONTROL_SIZES["border_width"],
            border_color=COLORS["control_border"], height=CONTROL_SIZES["main_button_height"],
            font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"),
        ).grid(row=0, column=1, rowspan=2, sticky="e", padx=16, pady=12)

        preferences = self.panel(self.settings_page)
        preferences.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 10))
        preferences.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(preferences, text="การเริ่มต้นและหน้าต่าง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(14, 8))
        self.startup_check = ctk.CTkCheckBox(
            preferences, text="เริ่มพร้อม Windows", variable=self.startup_enabled,
            command=self.toggle_autostart, checkbox_width=CONTROL_SIZES["checkbox"], checkbox_height=CONTROL_SIZES["checkbox"],
            corner_radius=CORNER_RADII["checkbox"], border_color=COLORS["checkbox_border"], fg_color=COLORS["blue_action"],
            hover_color=COLORS["blue_action_hover"], text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.startup_check.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        self.tray_check = ctk.CTkCheckBox(
            preferences, text="ย่อ/ปิดหน้าต่างไว้ที่ถาดระบบ", variable=self.close_to_tray,
            command=self.toggle_close_to_tray, checkbox_width=CONTROL_SIZES["checkbox"], checkbox_height=CONTROL_SIZES["checkbox"],
            corner_radius=CORNER_RADII["checkbox"], border_color=COLORS["checkbox_border"], fg_color=COLORS["blue_action"],
            hover_color=COLORS["blue_action_hover"], text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.tray_check.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 14))

        info = self.panel(self.settings_page)
        info.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 10))
        ctk.CTkLabel(info, text="ความปลอดภัยและเวอร์ชัน", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(info, text="●  รหัสผ่านเก็บใน Windows Credential Manager",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkLabel(info, text="ตรวจตาราง K-Room และแจ้งเตือนผ่านลำโพงเมื่อหมดเวลาจอง",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").pack(anchor="w", padx=16, pady=(0, 4))
        ctk.CTkLabel(info, text="labBoy Coworking  ·  v2.0", text_color=MUTED,
            font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").pack(anchor="w", padx=16, pady=(0, 14))

        appearance_card = self.panel(self.settings_page)
        appearance_card.grid(row=6, column=0, sticky="ew", padx=8, pady=(0, 10))
        appearance_card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(appearance_card, text="การแสดงผล", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["control"], "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        ctk.CTkLabel(appearance_card, text="ธีมจะเปลี่ยนเมื่อเปิดโปรแกรมครั้งถัดไป",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w").grid(
                row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        self.appearance_picker = ctk.CTkOptionMenu(
            appearance_card, variable=self.appearance_choice,
            values=list(THEME_KEYS), command=self.change_appearance,
            fg_color=LOG_BG, button_color=COLORS["button_neutral"],
            button_hover_color=COLORS["button_neutral_hover"], text_color=TEXT,
            dropdown_fg_color=WHITE, dropdown_text_color=TEXT,
            dropdown_hover_color=BLUE_PALE, corner_radius=CORNER_RADII["filter"],
            height=CONTROL_SIZES["filter_height"], width=190,
            font=(FONT_FAMILY, FONT_SIZES["secondary"]),
            dropdown_font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.appearance_picker.grid(row=0, column=1, rowspan=2, sticky="e", padx=16, pady=12)

        self.settings_nav_button = ctk.CTkButton(self.sidebar, text="ตั้งค่า", command=self.show_settings,
            fg_color=WHITE, hover_color=BLUE_PALE, text_color=TEXT,
            border_width=CONTROL_SIZES["border_width"], border_color=COLORS["card_border"],
            height=CONTROL_SIZES["main_button_height"], font=(FONT_FAMILY, FONT_SIZES["control"], "bold"))
        self.settings_nav_button.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 14))

    @staticmethod
    def panel(parent: tk.Widget, corner: int = CORNER_RADII["card"]) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent, fg_color=WHITE, corner_radius=corner,
            border_width=CONTROL_SIZES["border_width"], border_color=COLORS["card_border"],
        )

    @staticmethod
    def set_scrollbar_width(frame: ctk.CTkScrollableFrame, width: int) -> None:
        """ลดความกว้าง scrollbar ผ่าน CTkScrollbar ที่ CTkScrollableFrame สร้างไว้"""
        scrollbar = getattr(frame, "_scrollbar", None)
        if scrollbar is not None:
            try:
                scrollbar.configure(width=width)
            except (tk.TclError, TypeError, ValueError):
                pass

    @staticmethod
    def create_line_icon(parent: tk.Widget, kind: str, background: str,
                         foreground: str, size: int) -> tk.Canvas:
        """วาดไอคอนเส้นแบบเรียบด้วย Canvas เพื่อไม่พึ่ง emoji หรือแพ็กเกจไอคอนเพิ่ม"""
        canvas = tk.Canvas(parent, width=size, height=size, bg=background,
                           highlightthickness=0, borderwidth=0, relief="flat")
        s = float(size)
        if kind == "speaker":
            points = [0.18*s, 0.38*s, 0.38*s, 0.38*s, 0.68*s, 0.18*s,
                      0.68*s, 0.82*s, 0.38*s, 0.62*s, 0.18*s, 0.62*s]
            canvas.create_polygon(points, fill=foreground, outline=foreground)
            canvas.create_arc(0.44*s, 0.28*s, 0.91*s, 0.72*s,
                              start=300, extent=120, style=tk.ARC, outline=foreground, width=2)
            canvas.create_arc(0.50*s, 0.12*s, 1.10*s, 0.88*s,
                              start=300, extent=120, style=tk.ARC, outline=foreground, width=2)
        else:
            canvas.create_arc(0.26*s, 0.18*s, 0.74*s, 0.68*s,
                              start=0, extent=180, style=tk.ARC, outline=foreground, width=2)
            canvas.create_line(0.27*s, 0.43*s, 0.27*s, 0.70*s,
                               0.73*s, 0.70*s, 0.73*s, 0.43*s,
                               fill=foreground, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            canvas.create_line(0.20*s, 0.70*s, 0.80*s, 0.70*s, fill=foreground, width=2)
            canvas.create_oval(0.45*s, 0.76*s, 0.55*s, 0.86*s, fill=foreground, outline=foreground)
        return canvas

    def show_app_dialog(self, title: str, message: str, *, kind: str = "info",
                        confirm: bool = False, action_label: str = "ตกลง",
                        cancel_label: str = "ยกเลิก", parent: tk.Misc | None = None) -> bool:
        """แสดงกล่องโต้ตอบหน้าตาเดียวกับแอป และคืนค่า True เมื่อเลือกการกระทำหลัก"""
        parent = parent or self.root
        previous_grab = self.root.grab_current()
        accent = {"error": RED, "warning": AMBER, "success": GREEN, "info": BLUE}.get(kind, BLUE)
        result = False
        dialog = ctk.CTkToplevel(parent)
        dialog.title(title)
        dialog.geometry("480x250" if confirm else "460x220")
        dialog.resizable(False, False)
        dialog.transient(parent)
        dialog.configure(fg_color=BG)
        card = self.panel(dialog, corner=CORNER_RADII["dialog_card"])
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(card, text=title, text_color=accent,
            font=(FONT_FAMILY, FONT_SIZES["lead"], "bold"), anchor="w").pack(
                fill="x", padx=18, pady=(18, 8))
        ctk.CTkLabel(card, text=message, text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["body"]), anchor="w", justify="left",
            wraplength=410).pack(fill="both", expand=True, padx=18, pady=(0, 12))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=18, pady=(0, 16))

        def finish(accepted: bool) -> None:
            nonlocal result
            result = accepted
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass

        if confirm:
            ctk.CTkButton(actions, text=cancel_label, command=lambda: finish(False),
                fg_color=COLORS["button_neutral"], hover_color=COLORS["button_neutral_hover"],
                text_color=TEXT, border_width=CONTROL_SIZES["border_width"],
                border_color=COLORS["control_border"], height=CONTROL_SIZES["dialog_button_height"],
                width=CONTROL_SIZES["dialog_cancel_width"], font=(FONT_FAMILY, FONT_SIZES["body"], "bold")).pack(
                    side="right", padx=(8, 0))
        action = ctk.CTkButton(actions, text=action_label, command=lambda: finish(True),
            fg_color=accent, hover_color=COLORS["blue_dark"] if kind == "info" else accent,
            text_color=COLORS["white_text"], height=CONTROL_SIZES["dialog_button_height"],
            width=CONTROL_SIZES["dialog_save_width"] if confirm else CONTROL_SIZES["dialog_cancel_width"],
            font=(FONT_FAMILY, FONT_SIZES["body"], "bold"))
        action.pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        dialog.bind("<Escape>", lambda _event: finish(False))
        dialog.bind("<Return>", lambda _event: finish(True))
        dialog.grab_set()
        action.focus_set()
        dialog.wait_window()
        if previous_grab is not None:
            try:
                if previous_grab.winfo_exists():
                    previous_grab.grab_set()
            except tk.TclError:
                pass
        return result

    def select_mode(self) -> None:
        """อัปเดตคำอธิบายให้ตรงกับค่าที่เลือกในสวิตช์โหมด"""
        if self.mode.get() == "ใช้งานจริง":
            self.mode_hint.set("ประกาศเสียงตามกำหนดการอัตโนมัติ")
        else:
            self.mode_hint.set("อ่านตารางอย่างเดียว · ไม่สั่งเสียง")

    def toggle_mode(self) -> None:
        """รับค่าที่ CTkSwitch เปลี่ยนไว้ แล้วปรับข้อความและปุ่มหลัก"""
        if not self.mode_toggle_enabled:
            return
        self.select_mode()
        self.refresh_primary_action_label()

    def append_log(self, message: str) -> None:
        """เพิ่มเหตุการณ์ใหม่และปรับเฉพาะแถวที่มีข้อมูลเปลี่ยน"""
        event = self.parse_activity(message)
        if event is None:
            return
        booking_key = event.get("dedupe_key")
        if booking_key:
            if booking_key in self.seen_booking_event_keys:
                return
            self.seen_booking_event_keys.add(booking_key)
        now = datetime.now().timestamp()
        event["created_ts"] = str(now)
        if event["title"] in {"ประกาศเสียงสำเร็จ", "ประกาศเสียงไม่สำเร็จ", "ข้ามการประกาศ"}:
            event["retain_until"] = str(now + 600)
        event_signature = (event["time"], event["title"], event["subtitle"], event["color"])
        if self.activity_events:
            latest = self.activity_events[0]
            latest_signature = (latest["time"], latest["title"], latest["subtitle"], latest["color"])
            if (event["title"] == "ตรวจตารางเรียบร้อย"
                    and latest["title"] == event["title"]
                    and latest["subtitle"] == event["subtitle"]
                    and latest["color"] == event["color"]):
                latest["time"] = event["time"]
                latest["created_ts"] = event["created_ts"]
                self.render_activity_timeline()
                return
            if event_signature == latest_signature:
                return
        self.activity_events.insert(0, event)
        del self.activity_events[MAX_UI_LOG_LINES:]
        self.render_activity_timeline()

    def parse_activity(self, message: str) -> dict[str, str] | None:
        """สรุปบรรทัด log ที่สำคัญเป็นหัวข้อ รายละเอียด เวลา และสีประเภทเหตุการณ์"""
        cleaned = re.sub(r"#(?:[0-9a-fA-F]{3,8})\b", "", message).strip()
        time_match = re.search(r"\b(\d{2}:\d{2}:\d{2})\b", cleaned)
        stamp = time_match.group(1) if time_match else datetime.now().strftime("%H:%M:%S")
        event = {"title": "", "subtitle": "", "time": stamp, "color": BLUE}
        counts = dict(re.findall(r"(Windows|iOS|Android|Linux)=(\d+)", cleaned))
        if "สรุปรายการที่อ่านได้:" in cleaned:
            total = sum(int(value) for value in counts.values())
            event.update(title="ตรวจตารางเรียบร้อย", subtitle=f"พบรายการจองวันนี้ {total} รายการ", color=BLUE)
        elif "พบรายการ: ห้อง " in cleaned:
            match = re.search(r"พบรายการ: ห้อง (.*?) \| (\d{4}-\d{2}-\d{2} \d{2}:\d{2})–(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", cleaned)
            if not match:
                return None
            room, start, end = match.groups()
            room_number = ROOMS.get(room, {}).get("number", "—")
            event.update(
                title="ตรวจพบรายการจอง",
                subtitle=f"{room} · ROOM {room_number} · {start[-5:]}–{end[-5:]}",
                color=BLUE,
                dedupe_key=f"{room}|{start}|{end}",
            )
        elif "ข้ามรายการห้อง " in cleaned and "เพราะ" in cleaned:
            match = re.search(r"ข้ามรายการห้อง (.*?) เพราะ\s*(.*)$", cleaned)
            if not match:
                return None
            room, reason = match.groups()
            room_number = ROOMS.get(room, {}).get("number", "—")
            if "ระงับการจอง" in reason:
                reason_short, color = "ถูกระงับการจอง", RED
            elif "ไม่เคยพบสถานะกำลังใช้ห้อง" in reason:
                reason_short, color = "ไม่พบการเช็คอิน", AMBER
            elif "ไม่ทราบสถานะ" in reason or "แปลสีสถานะ" in reason:
                reason_short, color = "ไม่ทราบสถานะ", AMBER
            else:
                reason_short, color = reason.strip(), AMBER
            event.update(
                title="ข้ามการประกาศ",
                subtitle=f"{room} · ROOM {room_number} · {reason_short}",
                color=color,
            )
        elif "ถึงเวลาสิ้นสุดห้อง " in cleaned:
            match = re.search(r"ถึงเวลาสิ้นสุดห้อง (.*?) เวลา (\d{2}:\d{2})", cleaned)
            if not match:
                return None
            room, end_time = match.groups()
            room_number = ROOMS.get(room, {}).get("number", "—")
            event.update(title="ตรวจพบรายการที่ครบเวลา", subtitle=f"{room} · ROOM {room_number} · {end_time}", color=AMBER)
        elif "สั่งเล่นเสียงห้อง " in cleaned and "สำเร็จ" in cleaned:
            room_match = re.search(r"สั่งเล่นเสียงห้อง (.*?) \(", cleaned)
            room = room_match.group(1) if room_match else "ลำโพง"
            room_number = ROOMS.get(room, {}).get("number", "—")
            event.update(title="ประกาศเสียงสำเร็จ", subtitle=f"{room} · ROOM {room_number}", color=GREEN)
        elif "ลำโพงห้อง " in cleaned and "ERROR" in cleaned.upper():
            room_match = re.search(r"ลำโพงห้อง (.*?) ตอบ", cleaned)
            room = room_match.group(1) if room_match else "ลำโพง"
            room_number = ROOMS.get(room, {}).get("number", "—")
            event.update(title="ประกาศเสียงไม่สำเร็จ", subtitle=f"{room} · ROOM {room_number}", color=RED)
        elif "ERROR" in cleaned.upper():
            event.update(title="อ่านตารางไม่สำเร็จ", subtitle="กำลังลองอ่าน K-Room ใหม่", color=RED)
        elif "เริ่มโปรแกรมในโหมด" in cleaned:
            event.update(title="ระบบเริ่มทำงาน", subtitle=cleaned.split("เริ่มโปรแกรมในโหมด", 1)[-1].strip(), color=BLUE)
        elif "บันทึกรหัสผ่านไว้" in cleaned:
            event.update(title="บันทึกรหัสลำโพงแล้ว", subtitle="เก็บใน Windows Credential Manager", color=GREEN)
        elif "ทดสอบเสียงหนึ่งครั้ง" in cleaned:
            room_match = re.search(r"ห้อง (Windows|iOS|Android|Linux)", cleaned)
            room = room_match.group(1) if room_match else "ลำโพง"
            room_number = ROOMS.get(room, {}).get("number", "—")
            event.update(title="เริ่มทดสอบเสียง", subtitle=f"{room} · ROOM {room_number}", color=BLUE)
        elif "กำลังหยุด" in cleaned or "ระบบหยุดทำงานแล้ว" in cleaned:
            event.update(title="หยุดการตรวจตาราง", subtitle="ระบบหยุดทำงานตามคำสั่ง", color=AMBER)
        else:
            return None
        return event

    def render_activity_timeline(self) -> None:
        """อัปเดต Timeline จากแถวที่เตรียมไว้ โดยไม่ลบหรือสร้าง Widget ซ้ำ"""
        now = datetime.now().timestamp()
        retained = [
            event for event in self.activity_events
            if float(event.get("retain_until", "0") or 0) > now
        ]
        selected = retained[:len(self.activity_rows)]
        for event in self.activity_events:
            if len(selected) >= len(self.activity_rows):
                break
            if event not in selected:
                selected.append(event)
        visible = sorted(
            selected,
            key=lambda event: float(event.get("created_ts", "0") or 0),
            reverse=True,
        )
        signature = tuple(
            (event["time"], event["title"], event["subtitle"], event["color"])
            for event in visible
        )
        if signature == self._last_logs_signature:
            return
        self._last_logs_signature = signature
        if visible:
            self.activity_empty.grid_remove()
        else:
            self.activity_empty.grid(row=0, column=0, sticky="ew", pady=24)
        dot_colors = {GREEN: GREEN_SWITCH, AMBER: COLORS["event_amber"], BLUE: BLUE, RED: RED}
        for index, event in enumerate(visible):
            row = self.activity_rows[index]
            row["dot"].configure(text_color=dot_colors.get(event["color"], BLUE))
            row["title"].configure(text=event["title"])
            row["subtitle"].configure(text=event["subtitle"])
            row["time"].configure(text=event["time"])
            row["frame"].grid(row=index, column=0, sticky="ew", pady=4)
        for row in self.activity_rows[len(visible):]:
            row["frame"].grid_remove()

    def clear_logs(self) -> None:
        """ล้างเฉพาะ Timeline ในหน้าจอ โดยไม่ลบไฟล์ log ถาวร"""
        self.activity_events.clear()
        self.render_activity_timeline()

    def set_running(self, running: bool, label: str | None = None,
                    color: str | None = None) -> None:
        if running:
            self.start_button.configure(
                text="กำลังหยุด…" if self.stopping else "หยุดชั่วคราว",
                state="disabled" if self.stopping else "normal",
                fg_color=AMBER_PALE if not self.stopping else COLORS["button_neutral"],
                hover_color=COLORS["hover_warning"] if not self.stopping else COLORS["button_neutral_hover"],
                text_color=AMBER if not self.stopping else MUTED,
                text_color_disabled=MUTED,
                border_color=AMBER_BORDER if not self.stopping else COLORS["control_border"],
            )
        else:
            self.refresh_primary_action_label()
        self.mode_toggle_enabled = not running
        self.mode_switch.configure(state="normal" if not running else "disabled")
        if running:
            self.mode_hint.set("กำลังทำงาน · หยุดระบบก่อนเปลี่ยนโหมด")
        else:
            self.select_mode()
        testing = running and not self.is_monitor_session
        for button in self.room_test_buttons.values():
            button.configure(text="กำลังทดสอบเสียง…" if testing else "ทดสอบเสียง 1 ครั้ง")
            button.configure(state="disabled" if testing else "normal")
        # ปุ่มจัดการรหัสคงกดได้เสมอ เมื่อระบบทำงานจะถามและหยุด monitor ก่อนเปิดหน้าต่าง
        self.credential_button.configure(state="normal")
        if label:
            self.status_text.set(label)
        if color:
            self.set_status_color(color)
        else:
            self.update_tray_icon()

    def set_status_color(self, color: str) -> None:
        """ปรับสีจุด ข้อความ และพื้นหลังสถานะให้สอดคล้องกัน"""
        background = {
            GREEN: GREEN_PALE, BLUE: BLUE_PALE,
            AMBER: AMBER_PALE, RED: RED_PALE,
            MUTED: LOG_BG,
        }.get(color, LOG_BG)
        self.status_dot.configure(text_color=color)
        self.status_label.configure(text_color=color)
        self.status_pill.configure(fg_color=background)
        self.update_tray_icon()

    def refresh_primary_action_label(self) -> None:
        """ใช้ป้ายปุ่มหลักที่ตรงกับโหมดและข้อมูลรหัสปัจจุบัน"""
        if self.mode.get() == "ใช้งานจริง" and not self.saved_speaker_password:
            action_text = "ตั้งค่ารหัสลำโพง"
        elif self.has_started_monitor:
            action_text = "ทำงานต่อ"
        else:
            action_text = "เริ่มทดลอง" if self.mode.get() != "ใช้งานจริง" else "เริ่มทำงานจริง"
        self.start_button.configure(
            text=action_text, state="normal",
            fg_color=(COLORS["green_action"] if action_text == "ทำงานต่อ" else BLUE_PALE),
            hover_color=(COLORS["green_button_hover"] if action_text == "ทำงานต่อ" else COLORS["hover_blue"]),
            text_color=(COLORS["white_text"] if action_text == "ทำงานต่อ" else BLUE),
            border_width=CONTROL_SIZES["border_width"],
            border_color=(COLORS["border_green"] if action_text == "ทำงานต่อ" else COLORS["border_blue"]),
        )

    def auto_start_live(self) -> None:
        """เริ่มโหมดจริงหลังเปิดหน้าต่าง หากยังไม่มีรหัสให้ทำขั้นตอนบันทึกครั้งแรก"""
        self.mode.set("ใช้งานจริง")
        self.select_mode()
        if not self.saved_speaker_password:
            self.set_running(False, "ต้องตั้งค่ารหัสลำโพงก่อนเริ่ม", AMBER)
            self.empty_schedule.configure(text="ตั้งค่ารหัสลำโพงเพื่อเริ่มอ่านรายการจองวันนี้")
            self.next_sound_text.set("ตั้งค่ารหัสลำโพงเพื่อเริ่ม")
            self.next_sound_eta.set("—")
            self.last_check.set(
                "รหัสเก็บใน Windows Credential Manager · กด “ตั้งค่ารหัสลำโพง” เพื่อเริ่ม"
            )
            self.credential_status_label.configure(
                text="Windows ไม่สามารถอ่านรหัสที่บันทึกไว้ได้" if self.credential_store_error else "ต้องตั้งค่าครั้งแรก",
                text_color=RED if self.credential_store_error else MUTED,
            )
            if self.credential_store_error:
                self.last_check.set(f"เปิดที่เก็บรหัสผ่านไม่ได้: {self.credential_store_error}")
            return
        self.password.set("")
        self.start_monitor(automatic=True)

    def primary_action(self) -> None:
        """ปุ่มหลักสลับระหว่างหยุดชั่วคราว ทำงานต่อ หรือตั้งค่าครั้งแรก"""
        if self.process and self.process.poll() is None:
            if not self.stopping:
                self.stop_monitor()
            return
        if not self.saved_speaker_password and self.mode.get() == "ใช้งานจริง":
            self.open_credential_dialog()
            return
        self.start_monitor()

    def open_credential_dialog(self) -> None:
        """เปิดหน้าต่างจัดการรหัสผ่าน โดยไม่แสดงช่องรหัสบนหน้าแดชบอร์ด"""
        if self.process and self.process.poll() is None:
            if self.show_app_dialog(
                "หยุดระบบเพื่อจัดการรหัส",
                "รหัสใหม่จะถูกใช้เมื่อเริ่ม monitor ใหม่\n\nต้องการหยุดระบบและเปิดหน้าต่างจัดการรหัสหรือไม่?",
                kind="warning", confirm=True, action_label="หยุดและจัดการรหัส",
            ):
                self.pending_credential_open = True
                self.credential_restart_pending = True
                self.stop_monitor()
            return
        if self.credential_dialog is not None:
            try:
                self.credential_dialog.lift()
                self.credential_dialog.focus_force()
                return
            except tk.TclError:
                self.credential_dialog = None
        dialog = ctk.CTkToplevel(self.root)
        self.credential_dialog = dialog
        dialog.title("จัดการรหัสลำโพง")
        dialog.geometry(f"{CONTROL_SIZES['credential_dialog_width']}x{CONTROL_SIZES['credential_dialog_height']}")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(fg_color=BG)
        card = self.panel(dialog, corner=20)
        card.pack(fill="both", expand=True, padx=18, pady=18)
        ctk.CTkLabel(
            card, text="รหัสผ่านลำโพง", text_color=TEXT,
            font=(FONT_FAMILY, FONT_SIZES["lead"], "bold"), anchor="w",
        ).pack(fill="x", padx=22, pady=(22, 5))
        ctk.CTkLabel(
            card,
            text="รหัสจะถูกเก็บใน Windows Credential Manager ของบัญชี Windows นี้.",
            text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]), anchor="w", wraplength=390,
        ).pack(fill="x", padx=22, pady=(0, 18))
        self.password.set("")
        self.password_entry = ctk.CTkEntry(
            card, textvariable=self.password, show="•", height=CONTROL_SIZES["entry_height"],
            corner_radius=CORNER_RADII["metric"], border_color=COLORS["control_border"], fg_color=COLORS["entry_bg"],
            text_color=TEXT, font=(FONT_FAMILY, FONT_SIZES["emphasis"]),
            placeholder_text="รหัส admin ของลำโพง",
        )
        self.password_entry.pack(fill="x", padx=22)
        self.show_password_check = ctk.CTkCheckBox(
            card, text="แสดงรหัสผ่าน", variable=self.show_password,
            command=self.toggle_password, checkbox_width=CONTROL_SIZES["dialog_checkbox"], checkbox_height=CONTROL_SIZES["dialog_checkbox"],
            corner_radius=CORNER_RADII["checkbox"], border_color=COLORS["checkbox_border"], fg_color=COLORS["blue_action"],
            hover_color=COLORS["blue_action_hover"], text_color=MUTED, font=(FONT_FAMILY, FONT_SIZES["secondary"]),
        )
        self.show_password.set(False)
        self.show_password_check.pack(anchor="w", padx=22, pady=(12, 14))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=22, pady=(0, 20))
        ctk.CTkButton(
            actions, text="ยกเลิก", command=self.close_credential_dialog,
            fg_color=COLORS["button_neutral"], hover_color=COLORS["button_neutral_hover"], text_color=TEXT,
            corner_radius=CORNER_RADII["control"], height=CONTROL_SIZES["dialog_button_height"], width=CONTROL_SIZES["dialog_cancel_width"], font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
        ).pack(side="right", padx=(8, 0))
        ctk.CTkButton(
            actions, text="บันทึกและเริ่มทำงาน", command=self.save_password_and_start,
            fg_color=COLORS["green_action"], hover_color=COLORS["green_button_hover"], text_color=COLORS["white_text"],
            corner_radius=CORNER_RADII["control"], height=CONTROL_SIZES["dialog_button_height"], width=CONTROL_SIZES["dialog_save_width"], font=(FONT_FAMILY, FONT_SIZES["body"], "bold"),
        ).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", self.close_credential_dialog)
        self.password_entry.focus_set()

    def close_credential_dialog(self) -> None:
        dialog = self.credential_dialog
        self.credential_dialog = None
        self.credential_restart_pending = False
        self.password.set("")
        if dialog is not None:
            try:
                dialog.grab_release()
                dialog.destroy()
            except tk.TclError:
                pass

    def save_password_and_start(self) -> None:
        password = self.password.get()
        if not password:
            self.show_app_dialog("ยังไม่ได้กรอกรหัส", "กรอกรหัสผ่าน admin ของลำโพงก่อนบันทึก", kind="warning", parent=self.credential_dialog)
            if self.password_entry.winfo_exists():
                self.password_entry.focus_set()
            return
        try:
            save_speaker_password(password)
        except (OSError, AttributeError) as exc:
            self.show_app_dialog(
                "บันทึกรหัสผ่านไม่ได้",
                f"Windows Credential Manager บันทึกรหัสไม่สำเร็จ\n{exc}\n\nระบบยังไม่เริ่มส่งเสียง",
                kind="error", parent=self.credential_dialog,
            )
            return
        self.saved_speaker_password = password
        self.speaker_auth_error = False
        restart_after_save = self.credential_restart_pending
        self.credential_status_label.configure(text="บันทึกใน Windows แล้ว", text_color=GREEN)
        self.password.set("")
        self.mode.set("ใช้งานจริง")
        self.select_mode()
        self.close_credential_dialog()
        self.append_log("บันทึกรหัสผ่านไว้ใน Windows Credential Manager แล้ว")
        if restart_after_save:
            if self.show_app_dialog(
                "บันทึกรหัสใหม่แล้ว",
                "รหัสใหม่จะถูกส่งให้ monitor ตอนเริ่ม process เท่านั้น\n\nต้องการเริ่มระบบใหม่ตอนนี้หรือเริ่มภายหลัง?",
                kind="info", confirm=True, action_label="เริ่มระบบใหม่", cancel_label="เริ่มภายหลัง",
            ):
                self.start_monitor(automatic=True)
            else:
                self.set_running(False, "บันทึกรหัสแล้ว · พร้อมเริ่ม", MUTED)
                self.next_sound_text.set("เริ่มระบบเมื่อต้องการใช้รหัสใหม่")
                self.next_sound_eta.set("รอเริ่มระบบ")
        else:
            self.start_monitor(automatic=True)

    def start_monitor(self, automatic: bool = False) -> None:
        if self.process and self.process.poll() is None:
            return
        monitor_entry = MONITOR_EXE if IS_FROZEN else MONITOR_SCRIPT
        if not monitor_entry.is_file():
            missing_name = "room_speaker_monitor.exe" if IS_FROZEN else "room_speaker_monitor.py"
            self.show_app_dialog("ไม่พบไฟล์", f"หาไฟล์ {missing_name} ไม่พบ\n{monitor_entry}", kind="error")
            return
        live = self.mode.get() == "ใช้งานจริง"
        typed_password = self.password.get()
        password = typed_password or self.saved_speaker_password
        if live and typed_password and not self.saved_speaker_password:
            self.show_app_dialog(
                "บันทึกรหัสผ่านก่อนเริ่ม",
                "ใช้หน้าต่าง “จัดการรหัสลำโพง” เพื่อเก็บรหัสใน Windows Credential Manager ก่อนเริ่มระบบ",
                kind="info",
            )
            return
        if live and not password:
            if automatic:
                self.auto_start_live()
            else:
                self.open_credential_dialog()
            return
        if live and not automatic and not self.show_app_dialog(
            "ยืนยันโหมดใช้งานจริง",
            "โหมดนี้จะสั่งลำโพงให้เล่นเสียงเมื่อครบเวลาจอง\n\nต้องการเริ่มหรือไม่?",
            kind="warning", confirm=True, action_label="เริ่มใช้งานจริง",
        ):
            return
        try:
            command = self.monitor_command()
        except Exception as exc:
            self.show_app_dialog("ไม่พบ Python", f"เรียก Python ไม่สำเร็จ\n{exc}", kind="error")
            return
        if live:
            command.append("--live")
        env = os.environ.copy()
        env.update({
            "SCHEDULE_URL": self.schedule_url.get().strip(),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
        })
        if live:
            env["SPEAKER_PASSWORD"] = password
        else:
            env.pop("SPEAKER_PASSWORD", None)
        try:
            self.process = subprocess.Popen(
                command, cwd=str(APP_DIR), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self.show_app_dialog("เริ่มระบบไม่ได้", f"เปิดตัวตรวจตารางไม่สำเร็จ\n{exc}", kind="error")
            return
        self.set_sleep_prevention(True)
        self.stopping = False
        self.has_started_monitor = True
        self.observed_in_use_keys.clear()
        self.seen_booking_event_keys.clear()
        label = "กำลังทำงานจริง · ส่งเสียงเมื่อครบเวลา" if live else "กำลังทดลอง · ไม่ส่งเสียง"
        self.active_mode_label = label
        self.monitor_started_at = datetime.now()
        self.session_started_at = self.monitor_started_at
        self.session_finished_at = None
        self.is_monitor_session = True
        self.session_read_count = 0
        self.session_booking_count = 0
        self.session_speaker_successes = 0
        self.session_speaker_failures = 0
        self.last_successful_read = None
        self.next_poll_at = None
        self.monitor_error = False
        self.last_read_empty = False
        self.booking_alerts.clear()
        self.booking_alert_colors.clear()
        self.reset_important_alerts()
        self.load_persisted_sound_state()
        self.clear_schedule()
        self.audio_status_text.set(
            "เสียงล่าสุด: รอเหตุครบเวลา" if live else "เสียงล่าสุด: โหมดทดลองไม่ส่งเสียง"
        )
        self.audio_status_label.configure(text_color=GREEN if live else MUTED)
        self.set_running(True, "ระบบ: กำลังเริ่มตรวจตาราง", GREEN if live else BLUE)
        self.last_check.set("กำลังรอผลอ่าน K-Room ครั้งแรก…")
        self.refresh_session_summary()
        self.refresh_next_sound()
        self.append_log(f"เริ่มโปรแกรมในโหมด{'ใช้งานจริง' if live else 'ทดลอง'}")
        threading.Thread(target=self.read_process_output, daemon=True).start()

    def monitor_command(self) -> list[str]:
        if IS_FROZEN:
            if not MONITOR_EXE.is_file():
                raise FileNotFoundError(f"ไม่พบตัว monitor ที่แพ็กไว้: {MONITOR_EXE}")
            return [str(MONITOR_EXE)]
        py = shutil.which("py.exe") or shutil.which("py")
        if py:
            return [py, "-3", str(MONITOR_SCRIPT)]
        python = shutil.which("python.exe") or shutil.which("python")
        if python:
            return [python, str(MONITOR_SCRIPT)]
        if sys.executable and Path(sys.executable).name.lower() in {"python.exe", "pythonw.exe"}:
            return [sys.executable, str(MONITOR_SCRIPT)]
        raise RuntimeError("ไม่พบ Python Launcher หรือ Python ใน PATH")

    def read_process_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.events.put(("log", line.rstrip()))
        self.events.put(("exit", str(process.wait())))

    def process_events(self) -> None:
        try:
            while True:
                event_type, value = self.events.get_nowait()
                if event_type == "log":
                    self.handle_log(value)
                elif event_type == "exit":
                    code = int(value)
                    self.set_sleep_prevention(False)
                    stopped_by_user = self.stopping
                    good_exit = code == 0 or stopped_by_user
                    exit_label = (
                        "หยุดชั่วคราว · ไม่มีการประกาศเสียง" if good_exit and self.has_started_monitor else
                        "หยุดทำงานแล้ว" if good_exit else
                        "มีตัวตรวจหรืองานทดสอบอีกชุดทำงานอยู่" if code == 3 else
                        f"หยุดด้วยข้อผิดพลาด ({code})"
                    )
                    exit_color = (AMBER if self.has_started_monitor else MUTED) if good_exit else RED
                    if self.speaker_auth_error:
                        exit_label = "หยุดแล้ว · ต้องตรวจรหัสลำโพง"
                        exit_color = RED
                    self.set_running(False,
                                     exit_label,
                                     exit_color)
                    self.password.set("")
                    self.append_log("ระบบหยุดทำงานแล้ว" if good_exit else f"โปรแกรมจบด้วยรหัส {code}")
                    self.stopping = False
                    self.process = None
                    self.monitor_started_at = None
                    self.next_poll_at = None
                    if self.pending_credential_open:
                        self.pending_credential_open = False
                        self.root.after(120, self.open_credential_dialog)
                    elif self.pending_test_room:
                        room = self.pending_test_room
                        self.pending_test_room = None
                        resume_after = self.pending_test_resume
                        self.pending_test_resume = False
                        self.root.after(120, lambda selected=room, resume=resume_after:
                                        self._launch_speaker_test(selected, resume_monitor=resume))
                    elif self.resume_monitor_after_test:
                        self.resume_monitor_after_test = False
                        self.root.after(180, lambda: self.start_monitor(automatic=True))
                    if self.is_monitor_session:
                        self.session_finished_at = datetime.now()
                        self.is_monitor_session = False
                        self.refresh_session_summary()
                    self.refresh_next_sound()
        except queue.Empty:
            pass
        self.root.after(150, self.process_events)

    def handle_log(self, line: str) -> None:
        if not line:
            return
        self.append_log(line)
        if "สรุปรายการที่อ่านได้:" in line:
            now = datetime.now()
            self.last_successful_read = now
            self.next_poll_at = now + timedelta(seconds=POLL_SECONDS)
            self.monitor_error = False
            self.clear_important_alert("kroom-read")
            counts = dict(re.findall(r"(Windows|iOS|Android|Linux)=(\d+)", line))
            self.last_read_empty = bool(counts) and all(value == "0" for value in counts.values())
            self.session_read_count += 1
            self.session_booking_count = sum(int(value) for value in counts.values())
            if self.last_read_empty:
                if self.speaker_auth_error:
                    self.status_text.set("ไม่พบรายการวันนี้ · รหัสลำโพงต้องตรวจสอบ")
                    self.set_status_color(RED)
                else:
                    self.status_text.set("ระบบ: อ่านตารางแล้ว · ไม่พบรายการของ 4 ห้อง")
                    self.set_status_color(AMBER)
            else:
                if self.speaker_auth_error:
                    self.status_text.set("ตารางอ่านได้ · รหัสลำโพงต้องตรวจสอบ")
                    self.set_status_color(RED)
                else:
                    self.status_text.set("ระบบ: กำลังตรวจตาราง")
                    self.set_status_color(GREEN if self.mode.get() == "ใช้งานจริง" else BLUE)
            self.refresh_monitor_health()
            self.clear_schedule()
            if self.last_read_empty:
                self.empty_schedule.configure(text="ไม่พบรายการจองของวันนี้ใน 4 ห้องที่ติดตาม")
            self.refresh_session_summary()
        elif "พบรายการ: ห้อง " in line:
            match = re.search(r"พบรายการ: ห้อง (.*?) \| (.*?)–(.*?) \| สถานะ=(.*?) สี=(.*)$", line)
            if match:
                room, start, end, status, _color = match.groups()
                self.add_schedule_row(room, f"{start} – {end}", status)
        skip_match = re.search(r"ข้ามรายการห้อง (.*?) เพราะ (.*)$", line)
        if skip_match:
            room, reason = skip_match.groups()
            if "ไม่เคยพบสถานะกำลังใช้ห้อง" in reason:
                self.update_booking_alert(room, "ข้าม · ไม่พบสถานะใช้", AMBER)
            elif "ระงับการจอง" in reason:
                self.update_booking_alert(room, "ข้าม · ถูกระงับ", RED)
            elif "ไม่ทราบสถานะ" in reason or "แปลสีสถานะ" in reason:
                self.update_booking_alert(room, "ข้าม · สถานะไม่ชัด", AMBER)
        end_match = re.search(r"ถึงเวลาสิ้นสุดห้อง (.*?) เวลา (\d{2}:\d{2})", line)
        if end_match:
            room, end_time = end_match.groups()
            if "ไม่ได้สั่งลำโพง" in line:
                self.update_booking_alert(room, "ครบเวลา · โหมดทดลอง", BLUE, end_time)
            else:
                self.update_booking_alert(room, "กำลังส่งเสียง…", BLUE, end_time)
        if "สั่งเล่นเสียงห้อง " in line and "สำเร็จ" in line:
            for room in ROOMS:
                if f"ห้อง {room}" in line:
                    source = "แจ้งเตือน" if self.is_monitor_session else "ทดสอบ"
                    self.room_status[room].configure(
                        text=f"● {source}สำเร็จ", text_color=GREEN,
                    )
                    self.speaker_auth_error = False
                    self.credential_status_label.configure(
                        text="บันทึกใน Windows แล้ว", text_color=GREEN,
                    )
                    self.audio_status_text.set(f"เสียงล่าสุด: {source} · {room} · สำเร็จ")
                    self.audio_status_label.configure(text_color=GREEN)
                    if self.is_monitor_session:
                        self.session_speaker_successes += 1
                        self.refresh_session_summary()
                    self.clear_important_alert(f"speaker-failed:{source}:{room}")
                    self.clear_important_alert(f"speaker-failed:{room}")
                    self.clear_important_alert("speaker-auth-failed")
                    if self.is_monitor_session:
                        self.update_booking_alert(room, "ส่งเสียงแล้ว", GREEN)
        elif "ลำโพงห้อง " in line and "ERROR" in line.upper():
            auth_failure = (
                "HTTP 401" in line.upper()
                or "UNAUTHORIZED" in line.upper()
                or "AUTHENTICATION FAILED" in line.upper()
            )
            for room in ROOMS:
                if f"ห้อง {room}" in line:
                    source = "แจ้งเตือน" if self.is_monitor_session else "ทดสอบ"
                    self.room_status[room].configure(
                        text=f"● {source}ไม่สำเร็จ", text_color=RED,
                    )
                    self.audio_status_text.set(f"เสียงล่าสุด: {source} · {room} · ไม่สำเร็จ")
                    self.audio_status_label.configure(text_color=RED)
                    if self.is_monitor_session:
                        self.session_speaker_failures += 1
                        self.refresh_session_summary()
                    if self.is_monitor_session:
                        self.update_booking_alert(room, "ส่งเสียงไม่สำเร็จ", RED)
                    alert_source = "แจ้งเตือน" if self.is_monitor_session else "ทดสอบ"
                    if auth_failure:
                        self.speaker_auth_error = True
                        self.status_text.set("ระบบ: รหัสผ่านลำโพงไม่ผ่านการตรวจสอบ")
                        self.set_status_color(RED)
                        self.audio_status_text.set(f"เสียงล่าสุด: ห้อง {room} · รหัสผ่านไม่ผ่าน")
                        self.audio_status_label.configure(text_color=RED)
                        self.last_check.set(
                            "หยุดชั่วคราว แล้วเลือก “จัดการรหัสลำโพง” เพื่อตรวจสอบรหัส"
                        )
                        self.credential_status_label.configure(
                            text="ลำโพงปฏิเสธรหัสผ่าน · ตรวจสอบหลังหยุดระบบ",
                            text_color=RED,
                        )
                        self.show_important_alert(
                            "speaker-auth-failed", "ลำโพงปฏิเสธรหัสผ่าน",
                            "หยุดระบบชั่วคราว แล้วจัดการรหัสลำโพงก่อนเริ่มใหม่",
                        )
                    else:
                        self.show_important_alert(
                            f"speaker-failed:{alert_source}:{room}",
                            f"{alert_source}เสียงห้อง {room} ไม่สำเร็จ",
                            f"ตรวจสอบเครือข่าย Audio ID และสถานะของลำโพงห้อง {room}",
                        )
        if "ERROR" in line and "ลำโพงห้อง " not in line:
            if "ยกเลิกการเริ่มซ้ำ" in line or "อีกชุดทำงานอยู่แล้ว" in line:
                self.status_text.set("ระบบ: มีตัวตรวจหรืองานทดสอบอีกชุดทำงานอยู่")
                self.set_status_color(AMBER)
                self.show_important_alert(
                    "duplicate-process", "โปรแกรมทำงานซ้ำ",
                    "หยุดตัวตรวจตารางหรือการทดสอบเสียงชุดเดิมก่อนเริ่มใหม่",
                )
                return
            first_error = not self.monitor_error
            self.monitor_error = True
            self.status_text.set("ระบบ: อ่าน K-Room ไม่สำเร็จ · กำลังลองใหม่")
            self.set_status_color(RED)
            if first_error:
                self.show_important_alert(
                    "kroom-read", "อ่าน K-Room ไม่สำเร็จ",
                    "กำลังลองอ่านใหม่ หากข้อมูลไม่กลับมา ให้ตรวจเครือข่ายและการเข้าสู่ระบบ K-Room",
                )

    def refresh_monitor_health(self) -> None:
        """อัปเดตเวลาอ่านล่าสุด รอบตรวจถัดไป และแจ้งข้อมูล K-Room ที่เริ่มเก่า"""
        process = self.process
        if process is None or process.poll() is not None:
            return

        now = datetime.now()
        if self.last_successful_read is not None:
            age = (now - self.last_successful_read).total_seconds()
            last_text = self.last_successful_read.strftime("%H:%M:%S")
            if age > STALE_AFTER_SECONDS:
                was_healthy = not self.monitor_error
                self.monitor_error = True
                self.status_text.set("ระบบ: ข้อมูล K-Room เก่า · กำลังลองอ่านใหม่")
                self.set_status_color(RED)
                self.last_check.set(f"ข้อมูลเก่า · อ่านสำเร็จล่าสุด {last_text}")
                if was_healthy:
                    self.show_important_alert(
                        "kroom-read", "ข้อมูล K-Room เก่า",
                        "ไม่มีรอบอ่านตารางสำเร็จนานเกิน 90 วินาที กำลังลองใหม่",
                    )
                return
            if self.monitor_error:
                self.last_check.set(f"อ่านสำเร็จล่าสุด {last_text} · กำลังลองใหม่")
                return

            if self.last_read_empty:
                if self.speaker_auth_error:
                    self.status_text.set("ไม่พบรายการวันนี้ · รหัสลำโพงต้องตรวจสอบ")
                    self.set_status_color(RED)
                else:
                    self.status_text.set("ระบบ: อ่านตารางแล้ว · ไม่พบรายการของ 4 ห้อง")
                    self.set_status_color(AMBER)
            else:
                if self.speaker_auth_error:
                    self.status_text.set("ตารางอ่านได้ · รหัสลำโพงต้องตรวจสอบ")
                    self.set_status_color(RED)
                else:
                    self.status_text.set("ระบบ: กำลังตรวจตาราง")
                    self.set_status_color(GREEN if self.mode.get() == "ใช้งานจริง" else BLUE)
            seconds_left = max(0, int((self.next_poll_at - now).total_seconds())) if self.next_poll_at else 0
            self.last_check.set(
                f"อ่านล่าสุด {last_text} · รหัสลำโพงต้องตรวจสอบ"
                if self.speaker_auth_error else
                f"อ่านล่าสุด {last_text} · ตรวจอีกประมาณ {seconds_left} วิ"
            )
            return

        if self.monitor_started_at is not None:
            elapsed = (now - self.monitor_started_at).total_seconds()
            if elapsed > STALE_AFTER_SECONDS:
                was_healthy = not self.monitor_error
                self.monitor_error = True
                self.status_text.set("ระบบ: ยังอ่าน K-Room ไม่สำเร็จ · กำลังลองใหม่")
                self.set_status_color(RED)
                self.last_check.set("ยังไม่มีรอบที่อ่านตารางสำเร็จ")
                if was_healthy:
                    self.show_important_alert(
                        "kroom-read", "ยังอ่าน K-Room ไม่สำเร็จ",
                        "เกิน 90 วินาทีแล้วยังไม่มีรอบอ่านตารางสำเร็จ ตรวจเครือข่ายหรือการเข้าสู่ระบบ",
                    )
            elif self.monitor_error:
                self.last_check.set("รอบอ่านมีข้อผิดพลาด · กำลังลองใหม่")
            else:
                self.last_check.set("กำลังรอผลอ่าน K-Room ครั้งแรก…")

    def refresh_session_summary(self) -> None:
        """สรุประยะเวลารัน จำนวนรอบอ่าน รายการ และผลส่งเสียงในรอบล่าสุด"""
        if self.session_started_at is None:
            duration_text = "ยังไม่เริ่ม"
        else:
            end = self.session_finished_at or datetime.now()
            seconds = max(0, int((end - self.session_started_at).total_seconds()))
            hours, remainder = divmod(seconds, 3600)
            minutes, secs = divmod(remainder, 60)
            duration_text = f"{hours:02d}:{minutes:02d}:{secs:02d}"
        values = {
            "duration": duration_text,
            "reads": f"{self.session_read_count} รอบ",
            "bookings": f"{self.session_booking_count} รายการ",
            "audio": f"{self.session_speaker_successes} สำเร็จ · {self.session_speaker_failures} ไม่สำเร็จ",
        }
        for key, value in values.items():
            if self.session_summary_vars[key].get() != value:
                self.session_summary_vars[key].set(value)
        if hasattr(self, "activity_summary_text"):
            summary = (
                "อัปเดตแบบเรียลไทม์ · ผลการประกาศรอบนี้: "
                f"{self.session_speaker_successes} สำเร็จ · {self.session_speaker_failures} ไม่สำเร็จ"
            )
            if self.activity_summary_text.get() != summary:
                self.activity_summary_text.set(summary)

    def show_important_alert(self, key: str, title: str, message: str) -> None:
        """ค้างแถบแจ้งเตือนในหน้าหลัก โดยไม่แสดงเหตุเดิมซ้ำ"""
        self.update_tray_icon()
        if key in self.notified_alerts:
            return
        self.notified_alerts.add(key)
        self.pending_alerts[key] = (title, message)
        self._show_next_important_alert()

    def _show_next_important_alert(self) -> None:
        if self.active_alert_key is not None or not self.pending_alerts:
            return
        key = next(iter(self.pending_alerts))
        title, message = self.pending_alerts.pop(key)
        self.active_alert_key = key
        is_warning = key == "duplicate-process"
        color = AMBER if is_warning else RED
        action_color = COLORS["amber_action"] if is_warning else COLORS["red_action"]
        background = AMBER_PALE if is_warning else RED_PALE
        self.alert_banner.configure(fg_color=background, border_color=color)
        self.alert_title_label.configure(text=title, text_color=color)
        self.alert_message_label.configure(text=message)
        if key == "speaker-auth-failed":
            action_text, action = "แก้รหัสลำโพง", self.open_credential_dialog
        else:
            action_text, action = "เปิดบันทึก", self.open_log_folder
        self.alert_action_button.configure(
            text=action_text, command=action, fg_color=action_color,
            hover_color=COLORS["amber_dark"] if is_warning else COLORS["red_dark"],
            text_color=COLORS["white_text"],
        )
        self.alert_close_button.configure(text_color=color, hover_color=background)
        self.alert_banner.grid()

    def dismiss_important_alert(self) -> None:
        """ซ่อนเหตุปัจจุบันจนกว่าเงื่อนไขจะหายและเกิดเหตุใหม่"""
        if self.active_alert_key is None:
            return
        self.active_alert_key = None
        self.alert_banner.grid_remove()
        self._show_next_important_alert()

    def clear_important_alert(self, key: str) -> None:
        """ล้าง dedupe และแถบเมื่อระบบได้รับสัญญาณว่าเหตุขัดข้องหายแล้ว"""
        self.notified_alerts.discard(key)
        self.pending_alerts.pop(key, None)
        self.update_tray_icon()
        if self.active_alert_key == key:
            self.active_alert_key = None
            self.alert_banner.grid_remove()
            self._show_next_important_alert()

    def reset_important_alerts(self) -> None:
        self.notified_alerts.clear()
        self.pending_alerts.clear()
        self.active_alert_key = None
        if hasattr(self, "alert_banner"):
            self.alert_banner.grid_remove()

    def open_log_folder(self) -> None:
        """เปิดโฟลเดอร์บันทึกถาวรใน File Explorer"""
        try:
            LOG_DIR.mkdir(exist_ok=True)
            if os.name == "nt":
                os.startfile(str(LOG_DIR))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(LOG_DIR)])
            else:
                subprocess.Popen(["xdg-open", str(LOG_DIR)])
        except Exception as exc:
            self.show_app_dialog("เปิดโฟลเดอร์ไม่ได้", f"เปิดโฟลเดอร์ log ไม่สำเร็จ\n{exc}", kind="error")

    def clear_schedule(self) -> None:
        self.booking_records.clear()
        self.empty_schedule.configure(text="กำลังอ่านรายการจองจาก K-Room…")
        self.render_schedule_rows()

    def add_schedule_row(self, room: str, period: str, status: str) -> None:
        start_text, end_text = period.split(" – ", 1)
        try:
            start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(end_text, "%Y-%m-%d %H:%M")
        except ValueError:
            start_dt = end_dt = datetime.max
        key = f"{room}|{start_text}|{end_text}"
        alert = self.booking_alerts.get(key, self.default_booking_alert(status))
        if status == "กำลังใช้ห้อง":
            self.observed_in_use_keys.add(key)
        record: dict[str, object] = {
            "key": key, "room": room, "period": period, "status": status,
            "observed_in_use": status == "กำลังใช้ห้อง" or key in self.observed_in_use_keys,
            "start": start_dt, "end": end_dt,
            "alert": alert,
            "alert_color": self.booking_alert_colors.get(key, self.default_alert_color(alert)),
        }
        for index, existing in enumerate(self.booking_records):
            if existing.get("key") == key:
                self.booking_records[index] = record
                break
        else:
            self.booking_records.append(record)
        self.queue_schedule_render()
        self.refresh_next_sound()

    @staticmethod
    def default_booking_alert(status: str) -> str:
        if status == "กำลังใช้ห้อง":
            return "กำลังใช้ · รอหมดเวลา"
        if status == "เช็คอินแล้ว":
            return "เช็คอินแล้ว · รอใช้ห้อง"
        if status == "ระงับการจอง":
            return "ข้าม · ถูกระงับ"
        if status == "หมดเวลา":
            return "รอตรวจการใช้งาน"
        if status == "ไม่ทราบสถานะ":
            return "รอตรวจสถานะ"
        return "รอเริ่มใช้งาน"

    @staticmethod
    def default_alert_color(alert: str) -> str:
        if alert == "ส่งเสียงแล้ว":
            return GREEN
        if alert in {"ส่งเสียงไม่สำเร็จ", "ข้าม · ถูกระงับ"}:
            return RED
        if alert.startswith("ข้าม") or alert.startswith("รอตรวจ"):
            return AMBER
        if alert == "กำลังส่งเสียง…" or alert == "ครบเวลา · โหมดทดลอง":
            return BLUE
        return MUTED

    @staticmethod
    def compact_booking_period(item: dict[str, object]) -> str:
        start, end = item["start"], item["end"]
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            return str(item["period"])
        return f"{start:%H:%M}–{end:%H:%M}"

    def render_schedule_rows(self) -> None:
        """ปรับ Widget ของแถวที่เปลี่ยน และเก็บแถวเดิมไว้เพื่อลดการกะพริบ"""
        records = list(self.booking_records)
        selected_room = self.schedule_room_filter.get()
        selected_status = self.schedule_status_filter.get()
        if selected_status == "ครบเวลาแล้ว":
            selected_status = "หมดเวลา"
        if selected_room != "ทุกห้อง":
            records = [item for item in records if item["room"] == selected_room]
        if selected_status != "ทุกสถานะ":
            records = [item for item in records if item["status"] == selected_status]
        if self.schedule_sort.get() == "ใกล้หมดเวลาก่อน":
            now = datetime.now()
            completed_alerts = {
                "ส่งเสียงแล้ว", "ส่งเสียงไม่สำเร็จ", "ข้าม · ถูกระงับ", "ข้าม · ไม่พบสถานะใช้",
            }
            def end_order(item: dict[str, object]) -> tuple[int, float]:
                end = item.get("end")
                start = item.get("start")
                alert = str(item.get("alert", ""))
                status = str(item.get("status", ""))
                is_expired = status in {"หมดเวลา", "ครบเวลาแล้ว"}
                is_completed = alert in completed_alerts
                is_recent_in_use_expiry = (
                    is_expired
                    and bool(item.get("observed_in_use"))
                    and isinstance(end, datetime)
                    and 0 <= (now - end).total_seconds() <= STALE_AFTER_SECONDS
                    and not is_completed
                )
                is_waiting_to_broadcast = alert in {
                    "รอประกาศเสียง", "รอประกาศ", "กำลังส่งเสียง…",
                    "ครบเวลา · โหมดทดลอง", "ครบเวลาแล้ว · รอรอบตรวจถัดไป",
                }
                if status == "กำลังใช้ห้อง" or (is_expired and is_waiting_to_broadcast) or is_recent_in_use_expiry:
                    priority = 0
                    sort_time = end.timestamp() if isinstance(end, datetime) else float("inf")
                elif status in {"จองแล้ว", "เช็คอินแล้ว"} and isinstance(start, datetime) and start >= now:
                    priority = 1
                    sort_time = start.timestamp()
                else:
                    # รายการหมดเวลา/ดำเนินการเสร็จแล้วเรียงเวลาสิ้นสุดล่าสุดไว้ก่อน
                    priority = 2
                    sort_time = -(end.timestamp()) if isinstance(end, datetime) else float("inf")
                return priority, sort_time
            records.sort(key=end_order)
        else:
            records.sort(key=lambda item: item["start"])
        status_styles = {
            "จองแล้ว": (BLUE, BLUE_PALE),
            "ระงับการจอง": (RED, RED_PALE),
            "หมดเวลา": (AMBER, AMBER_PALE),
            "กำลังใช้ห้อง": (GREEN, GREEN_PALE),
            "เช็คอินแล้ว": (BLUE, BLUE_PALE),
            "ไม่ทราบสถานะ": (MUTED, LOG_BG),
        }
        signature_rows: list[tuple[object, ...]] = []
        for item in records:
            status = str(item["status"])
            alert = str(item["alert"])
            status_fg, status_bg = status_styles.get(status, (MUTED, LOG_BG))
            signature_rows.append((
                item.get("key"), str(item["room"]), self.compact_booking_period(item),
                status, status_fg, status_bg, alert,
                str(item.get("alert_color", self.default_alert_color(alert))),
            ))
        signature = tuple(signature_rows)
        if signature == self._last_bookings_signature:
            if not records:
                self.empty_schedule.configure(
                    text=("ไม่พบรายการที่ตรงกับตัวกรองนี้" if self.booking_records
                          else "ยังไม่มีข้อมูล · ระบบจะอ่านรายการจองวันนี้ให้อัตโนมัติ")
                )
                self.empty_schedule.grid(row=0, column=0, sticky="ew", pady=30)
            return
        self._last_bookings_signature = signature
        if not records:
            if self.booking_records:
                self.empty_schedule.configure(text="ไม่พบรายการที่ตรงกับตัวกรองนี้")
            self.empty_schedule.grid(row=0, column=0, sticky="ew", pady=30)
            for row in self.schedule_rows:
                row["frame"].grid_remove()
            return
        self.empty_schedule.grid_remove()
        while len(self.schedule_rows) < len(records):
            row_index = len(self.schedule_rows)
            frame = ctk.CTkFrame(
                self.schedule_list, fg_color=WHITE if row_index % 2 == 0 else COLORS["row_stripe"],
                corner_radius=CORNER_RADII["booking_row"],
            )
            frame.grid_columnconfigure(0, weight=3, uniform="schedule-cols")
            frame.grid_columnconfigure(1, weight=2, uniform="schedule-cols")
            frame.grid_columnconfigure(2, weight=2, uniform="schedule-cols")
            frame.grid_columnconfigure(3, weight=3, uniform="schedule-cols")
            frame.configure(height=CONTROL_SIZES["table_row_height"])
            frame.grid_propagate(False)
            room_cell = ctk.CTkFrame(frame, fg_color="transparent")
            room_cell.grid(row=0, column=0, sticky="ew", padx=(8, 3), pady=2)
            room_name = ctk.CTkLabel(room_cell, anchor="w", text_color=COLORS["text_primary"], font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"))
            room_name.grid(row=0, column=0, sticky="w")
            room_number = ctk.CTkLabel(room_cell, anchor="w", text_color=COLORS["text_muted"], font=(FONT_FAMILY, FONT_SIZES["caption"]))
            room_number.grid(row=0, column=1, sticky="w", padx=(8, 0))
            period_label = ctk.CTkLabel(frame, anchor="w", text_color=COLORS["text_primary"], font=(FONT_FAMILY, FONT_SIZES["emphasis"], "bold"))
            period_label.grid(row=0, column=1, sticky="w", padx=3, pady=2)
            status_label = ctk.CTkLabel(frame, anchor="w", corner_radius=CORNER_RADII["status_badge"], height=CONTROL_SIZES["status_badge_height"],
                                        font=(FONT_FAMILY, FONT_SIZES["secondary"], "bold"), padx=8, pady=1)
            status_label.grid(row=0, column=2, sticky="w", padx=3, pady=2)
            alert_label = ctk.CTkLabel(frame, anchor="w", text_color=COLORS["alert_text"], font=(FONT_FAMILY, FONT_SIZES["body"]))
            alert_label.grid(row=0, column=3, sticky="ew", padx=(5, 8), pady=2)
            self.add_tooltip(alert_label, lambda label=alert_label: str(label.cget("text")))
            self.schedule_rows.append({
                "frame": frame, "room": room_name, "room_number": room_number,
                "period": period_label, "status": status_label, "alert": alert_label,
            })
        for row_index, item in enumerate(records):
            widgets = self.schedule_rows[row_index]
            frame = widgets["frame"]
            frame.configure(fg_color=WHITE if row_index % 2 == 0 else COLORS["row_stripe"])
            frame.grid(row=row_index, column=0, sticky="ew", pady=2)
            room = str(item["room"])
            widgets["room"].configure(text=room)
            room_id = ROOMS.get(room, {}).get("number", "—")
            widgets["room_number"].configure(text=f"ROOM {room_id}")
            widgets["period"].configure(text=self.compact_booking_period(item))
            status = str(item["status"])
            status_fg, status_bg = status_styles.get(status, (MUTED, LOG_BG))
            status_display = "ครบเวลาแล้ว" if status == "หมดเวลา" else status
            widgets["status"].configure(
                text=f"●  {status_display}", text_color=status_fg, fg_color=status_bg,
            )
            alert = str(item["alert"])
            alert_marker = (
                "✓ " if alert == "ส่งเสียงแล้ว" else
                "! " if alert == "ส่งเสียงไม่สำเร็จ" else
                "– " if alert.startswith("ข้าม") else ""
            )
            widgets["alert"].configure(
                text=f"{alert_marker}{alert}", text_color=COLORS["alert_text"],
            )
        for widgets in self.schedule_rows[len(records):]:
            widgets["frame"].grid_remove()

    def queue_schedule_render(self) -> None:
        """รวมการวาดหลายแถวที่ตามกันมา ลดการวาดซ้ำระหว่างอ่านรายการจำนวนมาก"""
        if self.schedule_render_job is None:
            self.schedule_render_job = self.root.after(100, self._render_queued_schedule)

    def _render_queued_schedule(self) -> None:
        self.schedule_render_job = None
        self.render_schedule_rows()

    def update_booking_alert(self, room: str, message: str, color: str,
                             end_time: str | None = None) -> None:
        candidates = [item for item in self.booking_records if item["room"] == room]
        if end_time:
            candidates = [item for item in candidates
                          if isinstance(item["end"], datetime)
                          and item["end"].strftime("%H:%M") == end_time]
        if not candidates:
            return
        now = datetime.now()
        due = [item for item in candidates if isinstance(item["end"], datetime)
               and 0 <= (now - item["end"]).total_seconds() <= STALE_AFTER_SECONDS]
        if due:
            candidates = due
        pending = [item for item in candidates if item.get("alert") == "กำลังส่งเสียง…"]
        if pending:
            candidates = pending
        else:
            candidates.sort(key=lambda item: item["end"] if isinstance(item["end"], datetime) else datetime.min,
                            reverse=True)
        target = candidates[0]
        key = str(target["key"])
        self.booking_alerts[key] = message
        target["alert"] = message
        self.booking_alert_colors[key] = color
        target["alert_color"] = color
        if len(self.booking_alerts) > 500:
            for old_key in list(self.booking_alerts)[:100]:
                self.booking_alerts.pop(old_key, None)
                self.booking_alert_colors.pop(old_key, None)
        self.queue_schedule_render()

    def stop_monitor(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            self.set_running(
                False,
                "หยุดชั่วคราว · ไม่มีการประกาศเสียง" if self.has_started_monitor else "ยังไม่เริ่มตรวจตาราง",
                AMBER if self.has_started_monitor else MUTED,
            )
            return
        self.stopping = True
        self.set_running(True, "กำลังหยุดระบบ…", AMBER)
        self.append_log("กำลังหยุดตัวตรวจตาราง…")
        threading.Thread(target=self.terminate_process_tree, args=(process,), daemon=True).start()

    def set_sleep_prevention(self, enabled: bool) -> None:
        """ป้องกันเครื่อง Sleep ระหว่างตรวจตาราง โดยไม่บังคับให้จอเปิดค้าง"""
        if self.sleep_prevention_active == enabled:
            return
        try:
            set_system_sleep_prevention(enabled)
            self.sleep_prevention_active = enabled
            self.append_log(
                "ป้องกันเครื่อง Sleep ระหว่างตรวจตารางแล้ว" if enabled
                else "คืนค่าการจัดการ Sleep ของ Windows แล้ว"
            )
        except (AttributeError, OSError) as exc:
            self.append_log(f"ตั้งค่าป้องกันเครื่อง Sleep ไม่สำเร็จ: {exc}")

    @staticmethod
    def terminate_process_tree(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            subprocess.run(
                ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def test_speaker(self, room: str) -> None:
        device = ROOMS.get(room)
        if not device or not is_valid_ipv4(str(device.get("ip", ""))):
            self.show_app_dialog(
                "ยังไม่ได้ตั้งค่า IP ลำโพง",
                f"กรุณาตรวจ IP ของห้อง {room} ใน Settings > เปิดไฟล์ตั้งค่าอุปกรณ์ แล้วเปิดโปรแกรมใหม่",
                kind="warning",
            )
            return
        if not (self.password.get() or self.saved_speaker_password):
            self.open_credential_dialog()
            return
        if self.process and self.process.poll() is None:
            if self.stopping or self.pending_test_room is not None:
                self.show_app_dialog("กำลังหยุดระบบ", "รอให้การหยุดระบบเสร็จก่อนเริ่มทดสอบเสียง", kind="info")
                return
            if not self.is_monitor_session:
                self.show_app_dialog("กำลังทดสอบเสียง", "รอให้การทดสอบเสียงปัจจุบันเสร็จสิ้นก่อน", kind="info")
                return
            remaining = self.seconds_until_next_broadcast()
            if remaining is None:
                remaining_text = "ยังไม่มีรายการที่รอประกาศเสียง."
            else:
                minutes, seconds = divmod(remaining, 60)
                remaining_text = f"เวลาถึงรอบประกาศถัดไป: ประมาณ {minutes} นาที {seconds} วินาที."
            warning = "\n\nคำเตือน: รอบประกาศถัดไปเหลือไม่ถึง 2 นาที." if remaining is not None and remaining < 120 else ""
            device = ROOMS[room]
            confirmed = self.show_app_dialog(
                "หยุดตรวจชั่วคราวเพื่อทดสอบ",
                "ระบบประกาศอัตโนมัติจะหยุดชั่วคราวระหว่างทดสอบ และจะเริ่มตรวจต่อให้เอง.\n"
                f"{remaining_text}{warning}\n\nลำโพงห้อง {room} ({device['ip']}) จะเล่นเสียงจริงหนึ่งครั้ง.",
                kind="warning", confirm=True, action_label="หยุดและทดสอบ",
            )
            if confirmed:
                self.pending_test_room = room
                self.pending_test_resume = True
                self.stop_monitor()
            return
        device = ROOMS[room]
        if not self.show_app_dialog(
            "ยืนยันการทดสอบเสียง",
            f"ลำโพงห้อง {room} ({device['ip']}) จะเล่นเสียงจริงหนึ่งครั้ง\n\nพร้อมทดสอบหรือไม่?",
            kind="warning", confirm=True, action_label="ทดสอบเสียง",
        ):
            return
        self._launch_speaker_test(room, resume_monitor=False)

    def seconds_until_next_broadcast(self) -> int | None:
        now = datetime.now()
        candidates = [
            item for item in self.booking_records
            if item.get("observed_in_use")
            and isinstance(item.get("end"), datetime)
            and item.get("alert") not in {"ส่งเสียงแล้ว", "ส่งเสียงไม่สำเร็จ", "ข้าม · ถูกระงับ", "ข้าม · ไม่พบสถานะใช้"}
        ]
        if not candidates:
            return None
        due = [item for item in candidates if item["end"] <= now]
        if due:
            return max(0, int((self.next_poll_at - now).total_seconds())) if self.next_poll_at else POLL_SECONDS
        next_item = min(candidates, key=lambda item: item["end"])
        return max(0, int((next_item["end"] - now).total_seconds()))

    def _launch_speaker_test(self, room: str, *, resume_monitor: bool) -> None:
        device = ROOMS.get(room)
        if not device or not is_valid_ipv4(str(device.get("ip", ""))):
            self.show_app_dialog("ยังไม่ได้ตั้งค่า IP ลำโพง",
                f"กรุณาตรวจ IP ของห้อง {room} ใน Settings แล้วเปิดโปรแกรมใหม่", kind="warning")
            if resume_monitor:
                self.root.after(180, lambda: self.start_monitor(automatic=True))
            return
        password = self.password.get() or self.saved_speaker_password
        if not password:
            self.open_credential_dialog()
            return
        device = ROOMS[room]
        try:
            command = self.monitor_command() + ["--test-speaker", room]
        except Exception as exc:
            self.show_app_dialog("ไม่พบ Python", f"เรียก Python ไม่สำเร็จ\n{exc}", kind="error")
            if resume_monitor:
                self.root.after(180, lambda: self.start_monitor(automatic=True))
            return
        env = os.environ.copy()
        env.update({"SPEAKER_PASSWORD": password, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
        try:
            process = subprocess.Popen(
                command, cwd=str(APP_DIR), env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as exc:
            self.show_app_dialog("ทดสอบไม่ได้", f"เริ่มคำสั่งทดสอบไม่สำเร็จ\n{exc}", kind="error")
            if resume_monitor:
                self.root.after(180, lambda: self.start_monitor(automatic=True))
            return
        self.process = process
        self.resume_monitor_after_test = resume_monitor
        self.stopping = False
        self.room_status[room].configure(text="● กำลังทดสอบ", text_color=AMBER)
        self.audio_status_text.set(f"เสียงล่าสุด: ทดสอบ {room} กำลังเล่น…")
        self.audio_status_label.configure(text_color=AMBER)
        self.set_running(True, f"กำลังทดสอบลำโพงห้อง {room}", AMBER)
        self.append_log(f"ทดสอบเสียงหนึ่งครั้ง · ห้อง {room} · {device['ip']} · Audio ID {device['audio_id']}")
        threading.Thread(target=self.run_test_process, args=(process,), daemon=True).start()

    def run_test_process(self, process: subprocess.Popen[str]) -> None:
        try:
            output, _ = process.communicate(input="PLAY\n")
        except Exception as exc:
            output = f"ทดสอบเสียงไม่สำเร็จ: {exc}"
        for line in output.splitlines():
            self.events.put(("log", line.rstrip()))
        self.events.put(("exit", str(process.poll() if process.poll() is not None else 1)))

    def toggle_password(self) -> None:
        self.password_entry.configure(show="" if self.show_password.get() else "•")

    def update_clock(self) -> None:
        now = datetime.now()
        self.clock_time.set(now.strftime("%H:%M:%S"))
        thai_months = (
            "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
        )
        weekday = ("จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์")[now.weekday()]
        date_text = f"วัน{weekday}ที่ {now.day} {thai_months[now.month - 1]} {now.year + 543}"
        self.clock_date.set(date_text)
        self.booking_date_label.set(date_text)
        self.refresh_monitor_health()
        self.refresh_session_summary()
        self.refresh_next_sound()
        self.root.after(1000, self.update_clock)

    def load_persisted_sound_state(self) -> None:
        """ใช้ประวัติเดียวกับตัวตรวจ เพื่อให้สรุปเสียงถัดไปไม่ขัดกับการกันเสียงซ้ำ"""
        try:
            state = json.loads((APP_DIR / "room_speaker_state.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for field, destination in (("observed_in_use", self.observed_in_use_keys), ("triggered", None)):
            values = state.get(field, []) if isinstance(state, dict) else []
            if not isinstance(values, list):
                continue
            for signature in values:
                if not isinstance(signature, str):
                    continue
                parts = signature.split("|", 3)
                if len(parts) != 4:
                    continue
                _date, room, start_value, end_value = parts
                try:
                    start = datetime.fromisoformat(start_value).astimezone().replace(tzinfo=None)
                    end = datetime.fromisoformat(end_value).astimezone().replace(tzinfo=None)
                except ValueError:
                    continue
                key = f"{room}|{start:%Y-%m-%d %H:%M}|{end:%Y-%m-%d %H:%M}"
                if destination is not None:
                    destination.add(key)
                elif field == "triggered":
                    self.booking_alerts[key] = "ส่งเสียงแล้ว"
                    self.booking_alert_colors[key] = GREEN

    def refresh_next_sound(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            self.next_sound_text.set("ตัวตรวจหยุดอยู่")
            self.next_sound_eta.set("—")
            return
        if not self.is_monitor_session:
            self.next_sound_text.set("กำลังทดสอบลำโพง · ไม่ใช่รอบแจ้งเตือน")
            self.next_sound_eta.set("ทดสอบด้วยตนเอง")
            return
        if self.mode.get() != "ใช้งานจริง":
            self.next_sound_text.set("โหมดทดลอง · ไม่มีเสียงตามกำหนด")
            self.next_sound_eta.set("อ่านตารางอย่างเดียว")
            return
        now = datetime.now()
        candidates = [
            item for item in self.booking_records
            if item.get("observed_in_use")
            and isinstance(item.get("end"), datetime)
            and item.get("alert") not in {"ส่งเสียงแล้ว", "ข้าม · ถูกระงับ", "ข้าม · ไม่พบสถานะใช้"}
        ]
        # รายการที่เลยเวลานานแล้วไม่ควรบังรายการที่กำลังจะหมดเวลา
        recently_due = [
            item for item in candidates
            if 0 <= (now - item["end"]).total_seconds() <= STALE_AFTER_SECONDS
        ]
        if recently_due:
            item = min(recently_due, key=lambda entry: entry["end"])
            detail = "ครบเวลาแล้ว · รอรอบตรวจถัดไป"
            seconds_to_poll = max(
                1, int((self.next_poll_at - now).total_seconds())
            ) if self.next_poll_at else POLL_SECONDS
            self.next_sound_eta.set(f"ภายใน {seconds_to_poll} วินาที")
        else:
            upcoming = [item for item in candidates if item["end"] > now]
            if not upcoming:
                self.next_sound_text.set("ไม่มีรายการที่รอหมดเวลา")
                self.next_sound_eta.set("รอรายการใช้งานห้อง")
                return
            item = min(upcoming, key=lambda entry: entry["end"])
            end = item["end"]
            remaining = int((end - now).total_seconds())
            minutes, seconds = divmod(remaining, 60)
            if minutes >= 60:
                hours, remain_minutes = divmod(minutes, 60)
                until = f"อีก {hours} ชม. {remain_minutes} นาที"
            else:
                until = f"อีก {minutes} นาที" if minutes else f"อีก {seconds} วินาที"
            detail = f"ครบเวลา {end:%H:%M}"
            self.next_sound_eta.set(until)
        self.next_sound_text.set(f"ห้อง {item['room']} · {detail}")

    def save_preferences(self, show_error: bool = True) -> bool:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            PREFERENCES_FILE.write_text(
                json.dumps({
                    "close_to_tray": self.close_to_tray.get(),
                    "startup_enabled": self.startup_enabled.get(),
                    "appearance": THEME_KEYS.get(self.appearance_choice.get(), ACTIVE_THEME),
                    "schedule_url": self.schedule_url.get().strip(),
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except OSError as exc:
            if show_error:
                self.show_app_dialog("บันทึกการตั้งค่าไม่ได้", f"บันทึกไฟล์ตั้งค่าไม่สำเร็จ\n{exc}", kind="error")
            return False

    def save_schedule_url(self) -> None:
        """บันทึก URL ที่ monitor จะใช้เมื่อเริ่มรอบการตรวจครั้งถัดไป"""
        value = self.schedule_url.get().strip()
        if not value.startswith(("http://", "https://")):
            self.show_app_dialog("URL ไม่ถูกต้อง", "URL ต้องขึ้นต้นด้วย http:// หรือ https://", kind="warning")
            return
        if not self.save_preferences():
            return
        if self.process and self.process.poll() is None:
            message = "บันทึก URL แล้ว จะเริ่มใช้เมื่อหยุดและเริ่มตรวจตารางใหม่"
        else:
            message = "บันทึก URL แล้ว จะใช้เมื่อเริ่มตรวจตารางครั้งถัดไป"
        self.show_app_dialog("บันทึกแหล่งตารางแล้ว", message, kind="info")

    def open_room_config(self) -> None:
        """เปิดไฟล์รายการอุปกรณ์ส่วนตัวซึ่งอยู่นอก repository"""
        try:
            if not ROOM_CONFIG_PATH.is_file():
                ROOM_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(EXAMPLE_CONFIG_PATH, ROOM_CONFIG_PATH)
            if os.name == "nt":
                os.startfile(str(ROOM_CONFIG_PATH))
            else:
                subprocess.Popen(["xdg-open", str(ROOM_CONFIG_PATH)])
            self.show_app_dialog(
                "ไฟล์ตั้งค่าอุปกรณ์",
                "แก้ไขชื่อห้อง, หมายเลขห้อง, IP และ Audio ID แล้วปิดและเปิดโปรแกรมใหม่เพื่อโหลดค่า",
                kind="info",
            )
        except (OSError, AttributeError) as exc:
            self.show_app_dialog("เปิดไฟล์ตั้งค่าไม่ได้", str(exc), kind="error")

    def change_appearance(self, _label: str) -> None:
        if not self.save_preferences():
            self.appearance_choice.set(THEME_LABELS[ACTIVE_THEME])
            return
        self.show_app_dialog(
            "บันทึกธีมแล้ว",
            f"ธีม “{self.appearance_choice.get()}” จะเริ่มใช้เมื่อเปิดโปรแกรมครั้งถัดไป",
            kind="info",
        )

    def startup_command(self) -> str:
        if IS_FROZEN:
            parts = [sys.executable]
            if self.close_to_tray.get():
                parts.append("--start-tray")
            return subprocess.list2cmdline(parts)
        script = str(APP_DIR / "labboy_coworking_broadcast.py")
        pyw = shutil.which("pyw.exe") or shutil.which("pyw")
        if pyw:
            parts = [pyw, "-3", script]
        else:
            python = Path(sys.executable)
            pythonw = python.with_name("pythonw.exe") if python.name.lower() == "python.exe" else python
            parts = [str(pythonw if pythonw.is_file() else python), script]
        if self.close_to_tray.get():
            parts.append("--start-tray")
        return subprocess.list2cmdline(parts)

    def write_startup_registration(self, enabled: bool) -> None:
        if os.name != "nt":
            raise OSError("การเริ่มพร้อม Windows ใช้ได้เฉพาะ Windows")
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_KEY) as key:
            if enabled:
                winreg.SetValueEx(key, STARTUP_REGISTRY_VALUE, 0, winreg.REG_SZ, self.startup_command())
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_REGISTRY_VALUE)
                except FileNotFoundError:
                    pass

    def toggle_autostart(self) -> None:
        try:
            self.write_startup_registration(self.startup_enabled.get())
            self.save_preferences()
        except (OSError, ImportError) as exc:
            self.startup_enabled.set(not self.startup_enabled.get())
            self.show_app_dialog("เปลี่ยนการเริ่มพร้อม Windows ไม่ได้", str(exc), kind="error")

    def toggle_close_to_tray(self) -> None:
        if self.close_to_tray.get() and (os.name != "nt" or pystray is None):
            self.close_to_tray.set(False)
            self.show_app_dialog(
                "ยังใช้ถาดระบบไม่ได้",
                "ต้องติดตั้ง pystray ก่อน กรุณารัน “ติดตั้งส่วนประกอบ.bat” แล้วเปิดตัวเลือกนี้อีกครั้ง",
                kind="warning",
            )
            return
        self.save_preferences()
        if self.startup_enabled.get():
            try:
                self.write_startup_registration(True)
            except (OSError, ImportError) as exc:
                self.show_app_dialog("อัปเดตการเริ่มพร้อม Windows ไม่ได้", str(exc), kind="error")

    def tray_status(self) -> tuple[str, str]:
        if self.speaker_auth_error or self.monitor_error:
            return "ต้องตรวจสอบ", RED
        if self.process and self.process.poll() is None:
            if not self.is_monitor_session:
                return "กำลังทดสอบเสียง", AMBER
            return "กำลังตรวจตาราง", GREEN
        if self.has_started_monitor:
            return "หยุดชั่วคราว · ไม่มีการประกาศเสียง", AMBER
        return "ยังไม่เริ่ม", MUTED

    def build_tray_image(self) -> Image.Image:
        source = LOGO_PATH if LOGO_PATH.is_file() else ICON_PATH
        if source.is_file():
            image = Image.open(source).convert("RGBA")
            image.thumbnail((64, 64), Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            canvas.alpha_composite(image, ((64 - image.width) // 2, (64 - image.height) // 2))
        else:
            canvas = Image.new("RGBA", (64, 64), COLORS["surface"])
        _, color = self.tray_status()
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((45, 45, 63, 63), fill=color, outline=COLORS["surface"], width=2)
        return canvas

    def update_tray_icon(self) -> None:
        if self.tray_icon is None:
            return
        try:
            state, _color = self.tray_status()
            self.tray_icon.icon = self.build_tray_image()
            self.tray_icon.title = f"labboy Coworking · {state}"
        except Exception:
            # ไอคอนถาดเป็นตัวช่วยเสริม; ข้อผิดพลาดไม่ควรรบกวนระบบตรวจตาราง
            pass

    def ensure_tray_icon(self) -> bool:
        if self.tray_icon is not None:
            self.update_tray_icon()
            return True
        if pystray is None or os.name != "nt":
            return False
        try:
            image = self.build_tray_image()
            menu = pystray.Menu(
                pystray.MenuItem("เปิดหน้าต่าง", lambda _icon, _item: self.root.after(0, self.show_window), default=True),
                pystray.MenuItem("ออกจากโปรแกรม", lambda _icon, _item: self.root.after(0, self.exit_from_tray)),
            )
            state, _color = self.tray_status()
            self.tray_icon = pystray.Icon("labboy-coworking-broadcast", image,
                                         f"labboy Coworking · {state}", menu)
            self.tray_icon.run_detached()
            self.tray_thread_started = True
            return True
        except Exception as exc:
            self.append_log(f"สร้างไอคอนถาดระบบไม่สำเร็จ: {exc}")
            self.tray_icon = None
            return False

    def hide_to_tray(self) -> None:
        if not self.close_to_tray.get():
            return
        if not self.ensure_tray_icon():
            self.root.deiconify()
            self.show_app_dialog("ย่อไว้ที่ถาดระบบไม่ได้", "ไม่สามารถสร้างไอคอนถาดระบบได้ จึงเปิดหน้าต่างไว้", kind="warning")
            return
        self.root.withdraw()

    def show_window(self) -> None:
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()

    def on_window_minimize(self, _event: object = None) -> None:
        if self.close_to_tray.get():
            self.root.after(150, lambda: self.hide_to_tray() if self.root.state() == "iconic" else None)

    def exit_from_tray(self) -> None:
        self.show_window()
        self.root.after(100, lambda: self.close_app(force_exit=True))

    def close_app(self, force_exit: bool = False) -> None:
        if self.close_to_tray.get() and not force_exit:
            self.hide_to_tray()
            return
        if self.process and self.process.poll() is None:
            if not self.show_app_dialog(
                "ปิดโปรแกรม",
                "การปิดหน้าต่างจะหยุดตรวจตารางและหยุดการแจ้งเตือน\n\nต้องการปิดหรือไม่?",
                kind="warning", confirm=True, action_label="ปิดโปรแกรม",
            ):
                return
            self.terminate_process_tree(self.process)
        self.set_sleep_prevention(False)
        if self.private_fonts and os.name == "nt":
            try:
                gdi = ctypes.windll.gdi32
                gdi.RemoveFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
                gdi.RemoveFontResourceExW.restype = ctypes.c_int
                for font_path in self.private_fonts:
                    gdi.RemoveFontResourceExW(str(font_path), 0x10, None)
            except (AttributeError, OSError):
                pass
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.destroy()
        if self.win32_icon_handles and os.name == "nt":
            try:
                destroy_icon = ctypes.windll.user32.DestroyIcon
                destroy_icon.argtypes = [wintypes.HANDLE]
                destroy_icon.restype = wintypes.BOOL
                for icon_handle in self.win32_icon_handles:
                    destroy_icon(icon_handle)
            except (AttributeError, OSError, TypeError):
                pass

    def report_callback_exception(self, exc_type: type[BaseException],
                                  exc_value: BaseException,
                                  exc_traceback: object) -> None:
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            (APP_DIR / "gui_startup_error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        self.append_log(f"ข้อผิดพลาดในหน้าควบคุม: {exc_value}")


def main() -> None:
    try:
        set_windows_app_identity()
        from web_ui import run
        run()
    except Exception as exc:
        details = traceback.format_exc()
        try:
            (APP_DIR / "gui_startup_error.log").write_text(details, encoding="utf-8")
        except OSError:
            pass
        try:
            messagebox.showerror(
                "เปิดหน้าควบคุมไม่สำเร็จ",
                f"{exc}\n\nตรวจว่าติดตั้ง Microsoft Edge WebView2 Runtime แล้ว\nรายละเอียดอยู่ใน gui_startup_error.log",
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
