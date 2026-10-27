"""ทดสอบ UI ใน Edge แบบ headless ด้วย bridge จำลอง ไม่มีคำสั่งลำโพงจริง."""
import json
import os
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_contrast import contrast

from playwright.sync_api import sync_playwright

APP = Path(__file__).resolve().parents[1]
OUTPUT = Path(os.environ.get("BROADCAST_REVIEW_OUTPUT", str(APP / "build" / "ui-review")))


def sample_state():
    rooms = [
        {"name": name, "number": str(303 + i), "ip": f"192.0.2.{i + 1}",
         "audio_id": "13", "status": "ยังไม่มีผลทดสอบ", "status_kind": "neutral",
         "tint": "#EAF3FF", "tint_text": "#0055B8"}
        for i, name in enumerate(("Windows", "iOS", "Android", "Linux"))
    ]
    return {"running": True, "monitor_running": True, "is_live": True,
            "status": "กำลังตรวจตาราง", "status_kind": "green", "last_read": "18:59:30",
            "read_error": "", "auth_error": False, "room_cards": rooms,
            "bookings": [{"key": str(i), "room": rooms[i % 4]["name"],
                          "room_number": rooms[i % 4]["number"], "start": "16:00", "end": "19:00",
                          "status": "กำลังใช้ห้อง" if i < 2 else "หมดเวลา",
                          "alert": "รอตรวจสถานะ" if i < 2 else "ส่งเสียงแล้ว"} for i in range(8)],
            "activities": [{"time": "18:59:30", "title": "ตรวจตารางเรียบร้อย",
                            "subtitle": "พบรายการจอง 8 รายการ", "kind": "green"}],
            "metrics": {"runtime": "00:02:49", "reads": 6, "bookings": 8, "successes": 3, "failures": 0},
            "next_broadcast": {"room": "Linux", "room_number": "306", "detail": "ครบเวลา 19:00",
                               "eta": "1 นาที", "seconds": "60"},
            "settings": {"has_password": True, "schedule_url": "https://example.org/calendar",
                         "startup_enabled": False, "close_to_tray": False, "rooms": rooms},
            "now": "2026-10-27 18:59:00"}


class WebUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(channel="msedge", headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1280, "height": 940})
        self.addCleanup(self.page.close)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.add_init_script("window.sampleState = " + json.dumps(sample_state(), ensure_ascii=False) + ";" + """
            window.apiCalls = [];
            window.pywebview = {api: new Proxy({}, {get: (_, name) => async (...args) => {
                window.apiCalls.push([name, args]);
                if (name === 'startup' || name === 'get_state') return window.sampleState;
                return {ok:true,message:'บันทึกแล้ว',state:window.sampleState};
            }})};
        """)
        self.page.goto((APP / "web" / "index.html").as_uri())
        self.page.add_style_tag(content='*,*::before,*::after{transition:none!important;animation:none!important}')
        self.page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
        self.page.wait_for_function("window.current !== null || document.querySelector('#bookingRows tr')?.textContent.includes('Windows')")
        self.page.evaluate("document.fonts.ready")

    def test_table_filter_and_dom_reuse(self):
        first = self.page.locator('#bookingRows tr').first.element_handle()
        self.page.evaluate("renderBookings(current.bookings)")
        self.assertTrue(first.evaluate("node => node === document.querySelector('#bookingRows tr')"))
        self.page.locator('#statusFilter').select_option(label='ครบเวลาแล้ว')
        self.assertEqual(self.page.locator('#bookingRows tr:visible').count(), 6)
        self.assertFalse(self.errors)

    def test_password_dialog_and_test_confirmation(self):
        self.page.locator('#topPasswordBtn').click()
        self.assertTrue(self.page.locator('#passwordDialog').is_visible())
        self.page.locator('[data-close="passwordDialog"]').click()
        self.page.locator('.test-speaker-btn').first.click()
        self.assertTrue(self.page.locator('#confirmDialog').is_visible())
        self.assertIn('รอบประกาศถัดไป', self.page.locator('#confirmMessage').inner_text())
        self.page.locator('#confirmDialog button[value="cancel"]').click()
        self.assertNotIn('test_speaker', self.page.evaluate('apiCalls.map(item=>item[0])'))
        self.assertFalse(self.errors)

    def test_unsaved_settings_survive_refresh(self):
        self.page.locator('#viewToggleBtn').click()
        self.page.locator('#settingsScheduleUrl').fill('https://example.org/new-calendar')
        self.page.locator('#todayDateLabel').evaluate('() => update(current)')
        self.assertEqual(self.page.locator('#settingsScheduleUrl').input_value(), 'https://example.org/new-calendar')
        self.assertFalse(self.errors)

    def test_layout_six_rows_and_screenshots(self):
        for width, height in ((1280, 940), (1326, 678), (1100, 650)):
            self.page.set_viewport_size({"width": width, "height": height})
            self.page.screenshot(path=str(OUTPUT / f'dashboard-{width}x{height}.png'), animations='disabled')
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'), width)
            table = self.page.locator('.table-container').bounding_box()
            rows = self.page.locator('#bookingRows tr:visible')
            sixth = rows.nth(5).bounding_box()
            self.assertLessEqual(sixth['y'] + sixth['height'], table['y'] + table['height'] + 1)
        self.assertFalse(self.errors)

    def test_rendered_text_contrast_in_all_themes(self):
        for theme in ('light', 'dark', 'high_contrast'):
            self.page.evaluate('(theme) => { current.settings.appearance = theme; update(current); }', theme)
            self.page.locator('#viewToggleBtn').click()
            pairs = self.page.evaluate('''() => [...document.querySelectorAll('body *')].filter(el => {
                const rect=el.getBoundingClientRect();
                return rect.width && rect.height && rect.top < innerHeight && rect.bottom > 0 &&
                    [...el.childNodes].some(node=>node.nodeType===3 && node.textContent.trim()) &&
                    !['SCRIPT','STYLE','OPTION'].includes(el.tagName);
            }).map(el => {
                let parent=el, bg;
                while(parent){const c=getComputedStyle(parent).backgroundColor;
                    if(c.startsWith('rgb(')){bg=c;break;}parent=parent.parentElement;}
                const hex=c=>'#'+(c.match(/\\d+/g)||[]).slice(0,3).map(n=>(+n).toString(16).padStart(2,'0')).join('');
                return {text:el.textContent.trim().slice(0,55),fg:hex(getComputedStyle(el).color),bg:hex(bg||'rgb(255,255,255)')};
            })''')
            bad = [(pair, round(contrast(pair['fg'], pair['bg']), 2)) for pair in pairs
                   if len(pair['fg']) == 7 and contrast(pair['fg'], pair['bg']) < 4.5]
            self.page.screenshot(path=str(OUTPUT / f'settings-{theme}.png'), animations='disabled')
            self.assertFalse(bad, f'{theme}: {bad}')
            self.page.locator('#viewToggleBtn').click()


if __name__ == '__main__':
    unittest.main()
