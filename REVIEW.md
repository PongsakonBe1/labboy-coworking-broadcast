# ผลตรวจ UI และการทำงาน — 27 ตุลาคม 2569

ตรวจ source และทดสอบด้วยข้อมูลจำลองก่อนเผยแพร่ โดยไม่ส่งคำสั่งไปยังลำโพงจริง

## สิ่งที่แก้

| ก่อน | หลัง | ส่วนที่แก้ |
| --- | --- | --- |
| กรอง “ครบเวลาแล้ว” ไม่เจอค่าภายใน “หมดเวลา” | แปลงเฉพาะข้อความแสดงผลและกรองได้ | `web/booking_model.js`, `renderBookings` |
| เวลาเก่าอาจอยู่เหนือห้องที่กำลังใช้ | จัดสถานะสำคัญก่อน แล้วเรียงเวลาในกลุ่ม | `selectBookings` |
| ผลเสียงลงแถวสุดท้ายของห้อง | ผูกกับรายการที่ monitor กำลังประมวลผล | `_set_alert_by_room`, `_handle_log` |
| การทดสอบมืออาจทำให้ตารางขึ้นว่าส่งเสียงแล้ว | ผลทดสอบแยกจากผลตามตารางและตัวนับรอบนี้ | `_handle_log` |
| รายการที่ยกเลิกยังค้างใน GUI | เปลี่ยน snapshot เมื่อรับรายการของรอบใหม่ครบ | `_handle_log` |
| เปิดใหม่แล้วลืมผลประกาศที่ monitor จำไว้ | อ่าน `triggered` / `observed_in_use` จาก state เดียวกัน | `_load_sound_state` |
| banner อาจค้างรายการเก่าหรือแสดงระหว่างหยุด | ตัดรายการเลยช่วงเผื่อและเช็กสถานะ process | `_next_broadcast` |
| หน้าจอรีเฟรชล้างค่าที่กำลังแก้ | รักษา draft จนบันทึก | `fillSettings`, `saveSettingsSubmit` |
| สี “ไม่สำเร็จ” อาจถูกจับเป็น “สำเร็จ” | ให้เงื่อนไขล้มเหลวมีลำดับก่อน | `roomStatusKind` |
| อ่านสถานะ GUI แล้วซ่อนข้อความ process ล้มเหลว | คงสถานะผิดพลาดให้มองเห็น | `get_state` |
| reader รัน Python คนละ environment | ใช้ interpreter เดียวกับหน้าต่าง | `_monitor_command` |
| ปิดแอประหว่างทดสอบแล้วอาจกลับมาเริ่ม monitor | ยกเลิกคิว/การเริ่มต่อเมื่อปิดหรือสั่งหยุด | `_shutdown`, `_read_test_output` |
| helper อ่านรหัสอยู่ใน object ที่ส่งให้ JavaScript | bridge เปิดเฉพาะคำสั่งที่ UI ใช้ ไม่มีตัวอ่านรหัส | `DesktopAPI` |
| แถบ alert ว่างกินพื้นที่และตารางแถวที่ 6 ถูกตัด | ซ่อน alert ที่ไม่มีข้อความและคำนวณพื้นที่แนวตั้งใหม่ | `web/dashboard.css` |

## ดีไซน์

อ้างอิง [Figma Make ต้นฉบับ](https://www.figma.com/make/yc5Pr3QcdozfEGtfEWAK9s/Study-Room-Speaker-Dashboard) และ [หน้าเผยแพร่](https://italic-tempo-32462017.figma.site)

ใช้ header เต็มความกว้าง, sidebar ลำโพง, แถบเสียงรอบถัดไป, ตาราง และ timeline ใต้ตารางตามต้นฉบับ รักษาฟอนต์และไอคอนเดิม ใช้สีตัวอักษร/ขอบคอนโทรลที่ตรวจ contrast แล้ว และย่อพื้นที่ให้เหมาะกับจอเตี้ย จึงไม่บังคับ canvas 1280×940 เหมือน prototype

Figma connector คืน resource links ของ Make แต่ resource reader ใช้เปิด source links ต่อไม่ได้ และเครื่องมือ screenshot ไม่รองรับ Make จึงตรวจภาพและโครงหน้าจากหน้าเผยแพร่ของไฟล์เดียวกัน ไม่อ้างว่าได้ตรวจทุกสถานะของ Figma ผ่าน MCP

## ผลทดสอบ

- Python unittest 24 กรณี: ผ่าน
- JavaScript status/filter/priority/outcome suite: ผ่าน
- `check_contrast.py`: ผ่านคู่สี legacy และ Web UI ครบ light/dark/high_contrast
- ตรวจสีข้อความที่ render จริงในหน้าตั้งค่าทั้ง 3 ธีม: ผ่าน
- Layout ที่ 1280×940, 1326×678 (พื้นที่หน้าต่างบนจอ 1366×768), 1100×650: ตารางเห็นอย่างน้อย 6 แถว ไม่มี horizontal overflow ของ document
- ตรวจ DOM reuse, confirmation ทดสอบเสียง, draft ตั้งค่า: ผ่าน
- WebView2 จริงและ JavaScript/Python bridge: ผ่าน โดย mock รหัส, startup และ monitor
- สร้าง EXE ของ GUI และ monitor ด้วย PyInstaller: ผ่านทั้งสองไฟล์ใน `build/release`; ไม่เขียนทับ executable เดิมที่กำลังรัน และยังไม่ได้สั่งใช้งาน EXE ชุดใหม่กับลำโพงจริง
- monitor contract: รายการที่เคยใช้งานแล้วครบเวลาประกาศได้, รายการไม่เข้าใช้/ถูกระงับ/ไม่รู้จักสถานะ/เลยช่วงเผื่อ/อนาคต/โหมดทดลองไม่ประกาศ, รายการส่งแล้วไม่ส่งซ้ำ

รอบนี้ไม่ได้แก้ `room_speaker_monitor.py` และไม่ได้ทดสอบเสียงทางกายภาพซ้ำ

## ตรวจซ้ำ

```powershell
py -3 -m unittest discover -s tests -p "test_*.py" -v
node tests/test_booking_model.js
py -3 check_contrast.py
py -3 tests/smoke_webview.py
```

ภาพจากการทดสอบอยู่ใน `build/ui-review/` (ไม่ commit); ภาพตัวอย่างสาธารณะใน `docs/ui-preview.png` ใช้ข้อมูลจำลองและ IP เอกสาร `192.0.2.x`

ข้อจำกัด: การทดสอบจำลองยืนยันการแสดงผลและการเรียก process ได้ แต่ไม่ได้ยืนยันเสียงจริง, การล็อกอิน Windows รอบใหม่, หรือเครือข่าย/โครงสร้าง K‑Room ในอนาคต ต้องตรวจตามสภาพแวดล้อมเมื่อเปลี่ยนอุปกรณ์หรือเว็บ
