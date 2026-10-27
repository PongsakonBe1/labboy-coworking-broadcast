# คู่มือผู้ดูแลและการพัฒนาต่อ

## โครงสร้างระบบ

- `labboy_coworking_broadcast.py` เป็นจุดเริ่มโปรแกรมเดสก์ท็อป
- `web_ui.py` เชื่อม pywebview กับ monitor, Windows Credential Manager, tray และ startup
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

ใช้ `อัปเดตโปรแกรม.bat` ซึ่งเรียก `update_app.ps1` (UTF-8 BOM สำหรับ Windows PowerShell) เพื่อติดตั้งไฟล์จาก `build/release` ข้าง launcher หลังผู้ใช้ยืนยันจึงหยุด process ที่ตรวจ executable/script path ว่าเป็น installation นี้เท่านั้น สำรองไฟล์ใน `build/update-backups`, ตรวจ SHA256 หลังคัดลอก และคืนไฟล์เดิมเมื่อคัดลอกล้มเหลว จากนั้นเปิดแอปใหม่โดยคงโฟลเดอร์ runtime เดิม

`update_app.ps1 -CheckOnly` ตรวจ process/release แบบอ่านอย่างเดียว; `tests/test_updater.py` ใช้ไฟล์ executable จำลองและไม่หยุด process จริง

หน้าต่างปัจจุบันใช้ pywebview และ Microsoft Edge WebView2 Runtime; ตรวจ lifecycle ของ monitor และ dialog ผ่าน `web_ui.py` และการ render ผ่าน `web/`. อย่าเปิดแอประหว่างแก้/ตรวจ static code หากอาจมีรายการครบเวลาและส่งเสียงจริง

## ตรวจ regression อย่างปลอดภัย

`tests/test_desktop_controller.py` จำลอง credential/process, `tests/test_monitor_contract.py` จำลอง browser และคำสั่งลำโพง, `tests/test_web_ui.py` ใช้ Edge headless กับ JavaScript bridge จำลอง และ `tests/test_booking_model.js` ตรวจการเรียง/กรองสถานะ

รัน `python -m unittest discover -s tests -p "test_*.py" -v`, `node tests/test_booking_model.js` และ `python check_contrast.py`. การเปิด WebView จริงเพื่อทดสอบ bridge ใช้ `python tests/smoke_webview.py` ซึ่งปิดการอ่านรหัสและการเริ่ม monitor จริงไว้

สี Web UI อยู่ใน `web/dashboard.css`; ทุกครั้งที่แก้สีให้อัปเดต `WEB_WCAG_TEXT_PAIRS` / `WEB_WCAG_EDGE_PAIRS` ใน `check_contrast.py` และตรวจซ้ำ ส่วนไฟล์ฟอนต์ใน `web/fonts/` มีไว้ให้ local HTTP server เสิร์ฟได้ภายใน root เดียวกับหน้าเว็บ

GitHub Actions รันชุดตรวจบน Windows ทุก push/PR และเก็บภาพหน้าจอเป็น artifact. รายละเอียดผลตรวจครั้งล่าสุดอยู่ใน `REVIEW.md`
