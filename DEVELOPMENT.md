# คู่มือผู้ดูแลและการพัฒนาต่อ

## โครงสร้างระบบ

- `labboy_coworking_broadcast.py` เป็นจุดเริ่มโปรแกรมเดสก์ท็อป
- `web_ui.py` เชื่อม pywebview กับ monitor, Windows Credential Manager, tray และ startup
- `desktop_diagnostics.py` ตรวจแบบอ่านอย่างเดียว แยกจาก monitor และกฎประกาศเสียง; ไม่ import/แก้ `room_speaker_monitor.py`
- `web/` เก็บส่วนติดต่อผู้ใช้ HTML/CSS/JavaScript; monitor ยังคงเป็น process แยก
- `room_speaker_monitor.py` อ่านปฏิทิน K-Room ผ่าน Playwright และส่งคำสั่ง ISAPI ไปยังลำโพง Hikvision
- GUI รับ log จาก monitor ผ่าน stdout; อย่าเปลี่ยนรูปแบบ log โดยไม่ปรับ parser ใน GUI พร้อมกัน
- รหัสลำโพงเก็บใน Windows Credential Manager ของบัญชี Windows ที่เปิดโปรแกรม และส่งให้ child process ผ่าน environment ชั่วคราว
- `room_speaker_state.json` และ `logs/` เป็นข้อมูล runtime ของเครื่อง ห้ามนำขึ้น Git

## ตั้งสภาพแวดล้อมพัฒนา

ใช้ Python 3.11 ขึ้นไปบน Windows และติดตั้งแพ็กเกจจาก `requirements.txt` ใน virtual environment ก่อนรัน `labboy-coworking-broadcast.bat` หรือเปิด Python GUI โดยตรง

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Playwright ใช้ Microsoft Edge ที่ติดตั้งใน Windows ตามการตั้งค่าปัจจุบัน ไม่ต้องดาวน์โหลด Chromium เพิ่ม

## งานที่ต้องทำก่อนเผยแพร่ Public

- IP ลำโพงและค่าอุปกรณ์จริงอยู่ใน `%APPDATA%\labboy-coworking-broadcast\room_devices.json`; ใช้ `room_devices.example.json` ที่มี IP ว่างใน repository
- ตรวจ repository, log, state, ประวัติ Git และไฟล์เอกสารว่าไม่มีรหัสผ่าน, IP ภายใน หรือข้อมูลผู้ใช้
- อย่า commit Credential Manager, `.env`, log, state หรือไฟล์สำรอง
- ให้ผู้ดูแลหน่วยงานตรวจและอนุมัติการเผยแพร่ข้อมูลโครงสร้างระบบก่อนตั้ง repository เป็น Public

## เครื่องเคาน์เตอร์

แอปขอให้ Windows คงเครื่องตื่นระหว่าง monitor ทำงาน และคืนการจัดการ Sleep เมื่อหยุด monitor; จอภาพยังปิดได้ตามนโยบาย Windows การล็อกอินอัตโนมัติ, Windows Update, BIOS/UEFI และสิทธิ์บัญชีเป็นการตั้งค่าระดับหน่วยงาน ไม่ได้ตั้งโดยสคริปต์นี้



## Windows EXE packaging

`สร้างโปรแกรม EXE.bat` ใช้ PyInstaller สร้าง GUI และ monitor แยกเป็นสอง executable ลง `build/release` เพื่อให้ยังคงการทำงาน child-process และ log protocol เดิม ต้องเก็บไฟล์ทั้งคู่ไว้ข้างกันในโฟลเดอร์ที่เขียน log/state ได้ ตัว launcher เลือก GUI EXE เมื่อไฟล์ครบ; ถ้าไม่มีจะใช้ Python script ตามเดิม

การ build monitor ต้องใส่ `--runtime-hook pyinstaller_hooks/monitor_utf8_stdio.py` เพราะ [frozen interpreter ของ PyInstaller ไม่ประมวลผล environment variables ของ Python](https://pyinstaller.org/en/stable/advanced-topics.html#environment-variables-used-by-frozen-applications) การส่ง `PYTHONIOENCODING=utf-8` จาก GUI อย่างเดียวจึงไม่พอ บน Windows ภาษาไทยอาจส่ง pipe เป็น cp874 แต่ GUI ถอด UTF‑8 ทำให้ parser อ่าน summary/booking ไม่ได้ ทั้งที่ไฟล์ log UTF‑8 และตัว monitor ยังทำงานอยู่ Hook ตั้ง stdin/stdout/stderr ก่อนสร้าง logging handlers โดยไม่แก้ source monitor, ข้อความ log หรือ regex

หลัง build รัน `python tests/smoke_monitor_exe.py` เสมอ: คัดลอก EXE ไปโฟลเดอร์ชั่วคราว ตั้ง URL ให้ validation ปฏิเสธก่อนเริ่ม browser/lock แล้วตรวจ bytes ใน pipe ด้วย UTF‑8 strict ไม่อ่านรหัสหรือส่งคำสั่งอุปกรณ์ CI สร้างและทดสอบ monitor EXE จริงด้วย เพื่อจับปัญหาที่ไม่พบเมื่อรัน source Python

ใช้ `อัปเดตโปรแกรม.bat` ซึ่งเรียก `update_app.ps1` (UTF-8 BOM สำหรับ Windows PowerShell) เพื่อติดตั้งไฟล์จาก `build/release` ข้าง launcher หลังผู้ใช้ยืนยันจึงหยุด process ที่ตรวจ executable/script path ว่าเป็น installation นี้เท่านั้น สำรองไฟล์ใน `build/update-backups`, ตรวจ SHA256 หลังคัดลอก และคืนไฟล์เดิมเมื่อคัดลอกล้มเหลว จากนั้นเปิดแอปใหม่โดยคงโฟลเดอร์ runtime เดิม

`update_app.ps1 -CheckOnly` ตรวจ process/release แบบอ่านอย่างเดียว; `tests/test_updater.py` ใช้ไฟล์ executable จำลองและไม่หยุด process จริง

หน้าต่างปัจจุบันใช้ pywebview และ Microsoft Edge WebView2 Runtime; ตรวจ lifecycle ของ monitor และ dialog ผ่าน `web_ui.py` และการ render ผ่าน `web/`. อย่าเปิดแอประหว่างแก้/ตรวจ static code หากอาจมีรายการครบเวลาและส่งเสียงจริง

## ตรวจ regression อย่างปลอดภัย

`tests/test_desktop_controller.py` จำลอง credential/process, `tests/test_monitor_contract.py` จำลอง browser และคำสั่งลำโพง, `tests/test_web_ui.py` ใช้ Edge headless กับ JavaScript bridge จำลอง และ `tests/test_booking_model.js` ตรวจการเรียง/กรองสถานะ

รัน `python -m unittest discover -s tests -p "test_*.py" -v`, `node tests/test_booking_model.js` และ `python check_contrast.py`. การเปิด WebView จริงเพื่อทดสอบ bridge ใช้ `python tests/smoke_webview.py` ซึ่งปิดการอ่านรหัสและการเริ่ม monitor จริงไว้

สี Web UI อยู่ใน `web/dashboard.css`; ทุกครั้งที่แก้สีให้อัปเดต `WEB_WCAG_TEXT_PAIRS` / `WEB_WCAG_EDGE_PAIRS` ใน `check_contrast.py` และตรวจซ้ำ ส่วนไฟล์ฟอนต์ใน `web/fonts/` มีไว้ให้ local HTTP server เสิร์ฟได้ภายใน root เดียวกับหน้าเว็บ

GitHub Actions รันชุดตรวจบน Windows ทุก push/PR และเก็บภาพหน้าจอเป็น artifact. รายละเอียดผลตรวจครั้งล่าสุดอยู่ใน `REVIEW.md`

## Close lifecycle และชุดตรวจเบื้องต้น

`_on_closing` ทำงานบน WinForms UI thread ต้องคืน `False` ทันทีระหว่างรอการยืนยัน ห้ามเรียก `evaluate_js`, `destroy` หรือรอ process ตรงนั้น `_queue_close_confirmation` แสดง dialog ผ่าน worker; `confirm_exit` ตอบ bridge ทันทีแล้วให้ `_finish_exit` หยุด process tree, รอ reader และคืน Sleep/tray ก่อนเรียก `window.destroy` โดย `close_accepted=True` ขั้นตอน `_shutdown` ทำซ้ำได้และไม่ถือ controller lock ขณะรอ child process

การยกเลิก dialog เรียก `cancel_exit` เพื่อให้กดปิดครั้งต่อไปได้ ระหว่างปิด API ปฏิเสธงานใหม่และล้าง pending test/restart; ถ้าหยุด process tree ไม่สำเร็จจะคงหน้าต่างไว้พร้อมข้อความให้ลองปิดใหม่ ไม่ปิดแค่ process พ่อแล้วซ่อนปัญหา

`tests/smoke_shutdown.py` เปิด WebView2 จริงแยก process พร้อม monitor พ่อ–ลูกจำลอง แต่ละกรณีมี timeout และ cleanup เฉพาะ PID ที่ชุดทดสอบสร้าง ใช้ชื่อ tray ทดสอบเฉพาะตัว ไม่แตะ GUI mutex/รหัส/Run registry/monitor จริง CI ใช้ `--without-system-tray` เพราะ runner อาจไม่มี Explorer notification area; การซ่อนและหยุดไอคอน tray จริงทดสอบในชุด local ครบ 6 กรณี

`ทดสอบระบบเบื้องต้น.bat` เรียก `tests/run_basic_checks.py` รวบรวม unit/browser/native/contrast/EXE pipe เป็นรายงาน `build/basic-checks/*.txt` ชุดนี้ไม่ build หรืออัปเดตแอปเอง

## Built-in diagnostics และการแก้ไขจากหน้าจอ

`start_diagnostics` snapshot ค่าใน controller แล้วตรวจใน daemon worker โดยไม่ถือ controller lock ระหว่าง HTTP I/O ผลถูก publish ทีละแถวและส่งผ่าน `get_state`; ไม่ส่ง password/raw exceptions กลับ bridge จำกัดการเริ่มซ้ำ 60 วินาที และเมื่อ shutdown จะยกเลิกการตรวจที่เหลือ ไม่มี browser/process เพิ่มจาก diagnostics

`probe_calendar` ใช้ GET อ่าน HTML ขนาดจำกัด ตรวจ HTTP/SSL/timeout และ `#calendar` เท่านั้น ผลการอ่าน FullCalendar จริงอ้างอิง read_count/last_read ของ monitor รอบปัจจุบัน ไม่ถือว่าแค่ HTML มีปฏิทินแปลว่าอ่าน booking สำเร็จ `probe_speaker` ใช้ HTTP Digest GET capabilities ที่รองรับในอุปกรณ์ปัจจุบัน ไม่มี PUT/POST/play ใช้ username เดียวกับ SPEAKER_USERNAME ของ monitor HTTP 401 เสนอแก้รหัส, 403/404 หรือรูปแบบไม่ตรงให้ผู้ดูแลตรวจรุ่นอุปกรณ์ ไม่เหมารวมว่า auth ผิด

ผลเป็น snapshot พร้อมเวลา เปลี่ยนการตั้งค่าที่เกี่ยวข้อง/รหัส/เริ่มหยุด monitor จะ invalidate ผลเดิม; theme/startup อย่างเดียวไม่ invalidate การบันทึกรหัส/URL/อุปกรณ์ใหม่ระหว่างรันจะเสนอ restart เพราะ child process ใช้ env/config ตอนเริ่มเท่านั้น

`restart_monitor` ใช้ pending_restart เดิมหลังยืนยันจาก UI ไม่เปลี่ยนโหมด API pause จากผู้ใช้จะล้าง pending restart/test/resume; pause ภายในใช้ for_transition=True การตัดสินคิวหลัง reader จบอยู่ภายใต้ lock เดียวกัน ป้องกันคำสั่งหยุดสวนกับการเริ่มใหม่ โดยไม่แก้ regex/log protocol/trigger state ของ monitor

`tests/test_diagnostics.py` ใช้ HTTP server local และ requests/process จำลอง ครอบคลุมเว็บเปลี่ยนหน้า, timeout, 401/403, HTTP 200 ที่ body เป็น error, cancellation, snapshot stale, cooldown และ restart; `tests/test_web_ui.py` ตรวจ help view/confirmation/สี/ปุ่ม disabled/ขนาดจอและ DOM reuse

ปลายทาง capabilities ที่อ่านได้โดยไม่ challenge รหัสจะรายงานเพียงอ่านอุปกรณ์ได้ ยังยืนยันรหัสไม่ได้; ผลยืนยันรหัสต้องผ่าน Digest challenge และ response ที่ถูกต้อง ไม่ถือ HTTP 200 อย่างเดียวว่ารหัสถูก
