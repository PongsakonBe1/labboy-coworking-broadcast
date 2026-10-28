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


def diagnostic_report():
    return {'running':False,'stale':False,'checked_at':'18:59:45','rows':[
        {'key':'web','title':'การเชื่อมต่อ K‑Room','kind':'amber','detail':'เว็บไซต์ตอบช้า ระบบเดิมกำลังลองใหม่','action':'retry'},
        {'key':'monitor','title':'การอ่านรายการจองจริง','kind':'amber','detail':'ยังยืนยันผลอ่านล่าสุดไม่ได้','action':'restart'},
        {'key':'speaker:Linux','title':'ลำโพงห้อง Linux','kind':'red','detail':'อุปกรณ์ปฏิเสธรหัสผ่าน','action':'password'}]}


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
        self.motion_style = self.page.add_style_tag(content='*,*::before,*::after{transition:none!important;animation:none!important}')
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

    def open_diagnostic_report(self):
        self.page.evaluate('(report)=>{current.diagnostics=report;update(current);}', diagnostic_report())
        self.page.locator('#helpToggleBtn').click()

    def test_diagnostics_is_read_only_and_reuses_rows(self):
        self.page.locator('#helpToggleBtn').click()
        self.page.wait_for_function("apiCalls.some(item=>item[0]==='start_diagnostics')")
        calls=self.page.evaluate('apiCalls.map(item=>item[0])')
        self.assertNotIn('test_speaker',calls)
        self.assertNotIn('restart_monitor',calls)
        self.page.evaluate('(report)=>{current.diagnostics=report;update(current);}', diagnostic_report())
        first=self.page.locator('.diagnostic-row').first.element_handle()
        self.page.evaluate('update(current)')
        self.assertTrue(first.evaluate('(node)=>node===document.querySelector(".diagnostic-row")'))
        self.assertIn('พบปัญหา',self.page.locator('#diagnosticSummary').inner_text())

    def test_diagnostic_repair_requires_confirmation_and_can_open_password(self):
        self.open_diagnostic_report()
        self.page.locator('[data-repair="restart"]').click()
        self.assertIn('เหลือ',self.page.locator('#confirmMessage').inner_text())
        self.page.locator('#confirmDialog button[value="cancel"]').click()
        self.assertNotIn('restart_monitor',self.page.evaluate('apiCalls.map(item=>item[0])'))
        self.page.locator('[data-repair="restart"]').click()
        self.page.locator('#confirmButton').click()
        self.page.wait_for_function("apiCalls.some(item=>item[0]==='restart_monitor')")
        self.page.locator('[data-repair="password"]').click()
        self.assertTrue(self.page.locator('#passwordDialog').is_visible())
        self.page.keyboard.press('Escape')
        self.assertNotIn('save_password',self.page.evaluate('apiCalls.map(item=>item[0])'))

    def test_stale_diagnostic_results_cannot_apply_old_actions(self):
        self.open_diagnostic_report()
        self.page.evaluate('()=>{current.diagnostics.stale=true;update(current);}')
        self.assertTrue(self.page.locator('[data-repair="restart"]').is_disabled())
        self.assertTrue(self.page.locator('#runDiagnosticsBtn').is_enabled())

    def test_help_layout_and_contrast_in_all_themes(self):
        self.open_diagnostic_report()
        for theme in ('light','dark','high_contrast'):
            self.page.evaluate('(theme)=>{current.settings.appearance=theme;update(current);}',theme)
            self.check_visible_text_contrast('help/'+theme)
            self.page.evaluate('()=>{current.diagnostics.running=true;update(current);}')
            self.check_visible_text_contrast('help-running/'+theme)
            self.assertEqual(self.page.locator('#runDiagnosticsBtn').evaluate('(node)=>getComputedStyle(node).opacity'),'1')
            self.page.evaluate('()=>{current.diagnostics.running=false;update(current);}')
            for width,height in ((1280,940),(1326,678),(900,540)):
                self.page.set_viewport_size({'width':width,'height':height})
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth'),width)
                self.page.locator('#helpLogsBtn').scroll_into_view_if_needed()
                rect=self.page.locator('#helpLogsBtn').bounding_box()
                self.assertLessEqual(rect['y']+rect['height'],height)
            self.page.set_viewport_size({'width':1280,'height':940})
            self.page.locator('#helpTitle').scroll_into_view_if_needed()
            self.page.screenshot(path=str(OUTPUT/f'help-{theme}.png'))
        self.assertFalse(self.errors)

    def test_close_confirmation_is_not_duplicated_and_cancel_is_reported(self):
        self.page.evaluate('() => { window.showCloseConfirm(); window.showCloseConfirm(); }')
        self.assertTrue(self.page.get_by_role('dialog', name='หยุดและปิดโปรแกรมหรือไม่').is_visible())
        self.page.locator('#confirmDialog button[value="cancel"]').click()
        self.page.wait_for_function("apiCalls.some(item=>item[0]==='cancel_exit')")
        self.assertNotIn('confirm_exit', self.page.evaluate('apiCalls.map(item=>item[0])'))
        self.page.evaluate('() => { window.showCloseConfirm(); }')
        self.page.locator('#confirmButton').click()
        self.page.wait_for_function("apiCalls.some(item=>item[0]==='confirm_exit')")
        self.assertEqual(self.page.evaluate("apiCalls.filter(item=>item[0]==='confirm_exit').length"), 1)

    def test_closing_disables_new_work_and_retry_restores_controls(self):
        self.page.evaluate("() => { current.closing=true; current.status='กำลังหยุดและปิดโปรแกรม'; update(current); }")
        self.assertTrue(self.page.locator('#topActionBtn').is_disabled())
        self.assertTrue(self.page.locator('#topPasswordBtn').is_disabled())
        self.assertTrue(self.page.locator('.test-speaker-btn').first.is_disabled())
        self.page.evaluate('() => { current.closing=false; update(current); }')
        self.assertTrue(self.page.locator('#topActionBtn').is_enabled())
        self.assertTrue(self.page.locator('.test-speaker-btn').first.is_enabled())

    def test_completed_test_refreshes_only_the_target_room_status(self):
        button = self.page.locator('.test-speaker-btn').last.element_handle()
        button.evaluate('(node) => node.focus()')
        self.page.evaluate('''() => {
            const room=current.room_cards.find(room=>room.name==='Linux');
            room.status='ทดสอบเสียงสำเร็จ · 18:59:45'; room.status_kind='green';
            current.status='ทดสอบเสียงสำเร็จ'; current.status_kind='green'; update(current);
        }''')
        card = self.page.locator('.room-card').filter(has=self.page.locator('.room-card-title',has_text='Linux'))
        self.assertIn('ทดสอบเสียงสำเร็จ', card.locator('.room-status-pill').inner_text())
        self.assertIn('green',card.locator('.room-status-pill').get_attribute('class'))
        self.assertIn('ทดสอบเสียงสำเร็จ',self.page.locator('#statusText').inner_text())
        self.assertIn('ยังไม่มีผลทดสอบ',self.page.locator('.room-card').first.inner_text())
        self.assertTrue(button.evaluate('(node) => node === document.activeElement'))
        self.assertFalse(self.errors)

    def test_keyboard_shortcuts_keep_confirmation_and_do_not_send_audio(self):
        self.page.keyboard.press('Control+Shift+P')
        self.assertTrue(self.page.get_by_role('dialog',name='หยุดระบบชั่วคราว?').is_visible())
        self.page.locator('#confirmDialog button[value="cancel"]').click()
        self.page.keyboard.press('Alt+4')
        self.assertIn('Linux',self.page.locator('#confirmTitle').inner_text())
        self.page.keyboard.press('Escape')
        self.page.keyboard.press('Control+,')
        self.assertTrue(self.page.locator('#settingsView').is_visible())
        self.assertNotIn('pause_monitor',self.page.evaluate('apiCalls.map(item=>item[0])'))
        self.assertNotIn('test_speaker',self.page.evaluate('apiCalls.map(item=>item[0])'))

    def test_reduced_motion_respects_system_preference(self):
        self.motion_style.evaluate('(node) => node.remove()')
        self.page.emulate_media(reduced_motion='reduce')
        self.assertEqual(self.page.locator('.switch').evaluate('(node)=>getComputedStyle(node).transitionDuration'),'0s')

    def test_visible_controls_and_secondary_text_have_minimum_sizes(self):
        for width,height in ((1280,940),(1326,678)):
            self.page.set_viewport_size({'width':width,'height':height})
            for view in ('main','settings'):
                if view == 'settings': self.page.locator('#viewToggleBtn').click()
                small = self.page.evaluate('''() => [...document.querySelectorAll('button,select')].filter(el=>{
                    const r=el.getBoundingClientRect();return r.width>2 && r.height>2 && r.top>=0 && r.bottom<=innerHeight && r.height<35.9;
                }).map(el=>[el.id||el.className,el.getBoundingClientRect().height])''')
                self.assertFalse(small,str(small))
                small_text=self.page.evaluate('''() => [...document.querySelectorAll('p,.room-status-pill,.room-cell-sub,.badge,th,.timeline-subtitle,.timeline-time')].filter(el=>{
                    const r=el.getBoundingClientRect();return r.width>2&&r.height>2&&r.top>=0&&r.bottom<=innerHeight&&parseFloat(getComputedStyle(el).fontSize)<14;
                }).map(el=>[el.className,getComputedStyle(el).fontSize])''')
                self.assertFalse(small_text,str(small_text))
                if view == 'settings': self.page.locator('#viewToggleBtn').click()

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

    def test_scaled_displays_keep_controls_reachable(self):
        # จำลองพื้นที่ logical บนจอ 1366x768 ที่ 125/150%; ไม่ย่อตัวอักษรเพื่อฝืนให้ครบหกแถว.
        for scale in (1.25, 1.5):
            context = self.browser.new_context(
                viewport={'width': int(1326 / scale), 'height': int(678 / scale)},
                device_scale_factor=scale)
            try:
                page = context.new_page()
                page.add_init_script('window.sampleState=' + json.dumps(sample_state()) + ';' + '''
                    window.pywebview={api:{startup:async()=>sampleState,get_state:async()=>sampleState}};
                ''')
                page.goto((APP / 'web' / 'index.html').as_uri())
                page.evaluate("window.dispatchEvent(new Event('pywebviewready'))")
                page.wait_for_selector('.test-speaker-btn')
                self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),
                                     page.viewport_size['width'])
                page.locator('.test-speaker-btn').last.click()
                self.assertTrue(page.get_by_role('dialog').is_visible())
                page.keyboard.press('Escape')
                page.locator('#viewToggleBtn').click()
                page.locator('#saveRoomConfigBtn').scroll_into_view_if_needed()
                rect = page.locator('#saveRoomConfigBtn').bounding_box()
                self.assertGreaterEqual(rect['y'], 0)
                self.assertLessEqual(rect['y'] + rect['height'], page.viewport_size['height'])
                page.screenshot(path=str(OUTPUT / f'settings-scale-{scale}.png'))
            finally:
                context.close()

    def test_rendered_text_contrast_in_all_themes(self):
        for theme in ('light', 'dark', 'high_contrast'):
            self.page.evaluate('(theme) => { current.settings.appearance = theme; update(current); }', theme)
            for view in ('dashboard','settings','details','password'):
                if view == 'settings': self.page.locator('#viewToggleBtn').click()
                if view == 'details': self.page.locator('.room-card-badge').first.click()
                if view == 'password': self.page.locator('#topPasswordBtn').click()
                self.check_visible_text_contrast(f'{theme}/{view}')
                if view == 'settings':
                    self.page.screenshot(path=str(OUTPUT / f'settings-{theme}.png'), animations='disabled')
                    self.page.locator('#viewToggleBtn').click()
                if view in ('details','password'): self.page.keyboard.press('Escape')

    def check_visible_text_contrast(self, label):
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
        self.assertFalse(bad, f'{label}: {bad}')


if __name__ == '__main__':
    unittest.main()
