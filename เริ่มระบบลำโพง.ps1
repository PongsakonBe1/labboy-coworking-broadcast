$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'room_speaker_monitor.py'

Write-Host 'K-ROOM Room Speaker Monitor' -ForegroundColor Cyan
Write-Host 'โหมดใช้งานจริง: เมื่อถึงเวลาสิ้นสุด จะสั่งลำโพงให้เล่นเสียง'
Write-Host 'กรุณากรอกรหัสผ่าน admin ของลำโพง (ตัวอักษรจะไม่แสดงบนหน้าจอ)'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Host "ไม่พบไฟล์สคริปต์: $scriptPath" -ForegroundColor Red
    Read-Host 'กด Enter เพื่อปิดหน้าต่าง'
    exit 1
}

$pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    Write-Host 'ไม่พบ Python ใน PATH กรุณาติดตั้ง Python ก่อน' -ForegroundColor Red
    Read-Host 'กด Enter เพื่อปิดหน้าต่าง'
    exit 1
}

$securePassword = Read-Host 'รหัสผ่านลำโพง' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:SPEAKER_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:SCHEDULE_URL = 'https://k-room.icit.kmutnb.ac.th/web/reserve/calendar'
    & $pythonCommand.Source $scriptPath --live
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:SPEAKER_PASSWORD -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

Write-Host ''
Write-Host 'โปรแกรมหยุดทำงานแล้ว (กด Ctrl+C เพื่อหยุดระหว่างทำงาน)'
Read-Host 'กด Enter เพื่อปิดหน้าต่าง'
exit $exitCode
