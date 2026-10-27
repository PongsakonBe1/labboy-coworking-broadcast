#!/usr/bin/env python3
"""ตรวจ WCAG contrast จาก design tokens โดยไม่ import หรือเปิดตัวแอป."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name("labboy_coworking_broadcast.py")
TOKEN_NAMES = {"DESIGN_TOKENS", "WCAG_TEXT_PAIRS", "WCAG_EDGE_PAIRS"}
WEB_CSS_FILE = SOURCE.parent / "web" / "dashboard.css"
WEB_WCAG_TEXT_PAIRS = [
    ("main on card", "text-main", "bg-surface", 4.5),
    ("main on active row", "text-main", "color-green-soft", 4.5),
    ("secondary on card", "text-sub", "bg-surface", 4.5),
    ("secondary on sidebar", "text-sub", "bg-sidebar", 4.5),
    ("muted on card", "text-muted", "bg-surface", 4.5),
    ("muted on sidebar", "text-muted", "bg-sidebar", 4.5),
    ("muted on table header", "text-muted", "bg-inner", 4.5),
    ("blue text on surface", "color-blue", "bg-surface", 4.5),
    ("blue text on banner/button", "color-blue", "color-blue-soft", 4.5),
    ("green status", "color-green", "color-green-soft", 4.5),
    ("amber status", "color-amber", "color-amber-soft", 4.5),
    ("red status", "color-red", "color-red-soft", 4.5),
    ("gray badge", "text-sub", "color-gray-soft", 4.5),
    ("primary action", "on-action", "action-blue", 4.5),
    ("resume action", "on-action", "action-green", 4.5),
]
WEB_WCAG_EDGE_PAIRS = [
    ("control border on surface", "control-border", "bg-surface", 3.0),
    ("control border on pale button", "control-border", "color-blue-soft", 3.0),
    ("switch off track", "switch-off", "bg-surface", 3.0),
    ("switch active track", "action-green", "bg-surface", 3.0),
    ("warning control border", "color-amber-border", "color-amber-soft", 3.0),
    ("scrollbar thumb", "scrollbar", "bg-inner", 3.0),
]


def read_web_tokens() -> dict[str, dict[str, str]]:
    source = WEB_CSS_FILE.read_text(encoding="utf-8")
    palettes = {}
    for theme in ("light", "dark", "high_contrast"):
        match = re.search(r'\[data-theme="' + theme + r'"\]\s*\{([^}]+)\}', source)
        if not match:
            raise ValueError(f"ไม่พบ web theme {theme}")
        palettes[theme] = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})", match.group(1)))
    return palettes


def read_tokens(path: Path) -> dict[str, object]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any(name in TOKEN_NAMES for name in names):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"{names}: ต้องเป็นค่าคงที่ที่อ่านได้") from exc
                for name in names:
                    if name in TOKEN_NAMES:
                        found[name] = value
    missing = TOKEN_NAMES - found.keys()
    if missing:
        raise ValueError("ไม่พบ token: " + ", ".join(sorted(missing)))
    return found


def linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        raise ValueError(f"สีไม่ถูกต้อง: {color!r}")
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def contrast(first: str, second: str) -> float:
    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    values = read_tokens(SOURCE)
    palettes = values["DESIGN_TOKENS"]
    failures = 0
    for group_name, threshold_label in (("WCAG_TEXT_PAIRS", "text"), ("WCAG_EDGE_PAIRS", "edge")):
        print(f"\n{threshold_label.upper()} CONTRAST")
        for theme, label, fg_key, bg_key, minimum in values[group_name]:
            palette = palettes[theme]["colors"]
            ratio = contrast(palette[fg_key], palette[bg_key])
            passed = ratio >= minimum
            print(f"{'PASS' if passed else 'FAIL'} [{theme}] {label}: {ratio:.2f}:1 (min {minimum:.1f}:1)")
            failures += not passed
    print("\nWEB UI CONTRAST")
    for theme, palette in read_web_tokens().items():
        for label, foreground, background, minimum in WEB_WCAG_TEXT_PAIRS + WEB_WCAG_EDGE_PAIRS:
            ratio = contrast(palette[foreground], palette[background])
            passed = ratio >= minimum
            print(f"{'PASS' if passed else 'FAIL'} [web/{theme}] {label}: {ratio:.2f}:1 (min {minimum:.1f}:1)")
            failures += not passed
    print(f"\nผลรวม: {'ผ่านทุกคู่' if not failures else f'{failures} คู่ยังไม่ผ่าน'}")
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, SyntaxError, ValueError, KeyError, TypeError) as exc:
        print(f"ตรวจไม่ได้: {exc}", file=sys.stderr)
        raise SystemExit(2)
