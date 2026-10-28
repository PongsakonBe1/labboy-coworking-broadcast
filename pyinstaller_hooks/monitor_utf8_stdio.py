"""กำหนด pipe ของ monitor EXE เป็น UTF-8 ก่อนสร้าง logging handlers.

Frozen interpreter ไม่อ่าน PYTHONIOENCODING แบบ Python script ปกติ จึงต้อง
ตั้ง stream โดยตรง รักษาข้อความ log/regex และกฎการส่งเสียงเดิมทั้งหมด.
"""
import sys


for _stream_name in ("stdin", "stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
