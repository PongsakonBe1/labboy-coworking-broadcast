$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'room_speaker_monitor.py'

Write-Host 'ทดสอบเสียงลำโพงเพียง 1 เครื่องและ 1 ครั้ง' -ForegroundColor Yellow
Write-Host 'การทดสอบนี้จะทำให้ลำโพงที่เลือกเล่นเสียงจริง'

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

Write-Host ''
Write-Host 'ห้องที่เลือกได้: Windows, iOS, Android, Linux'
$room = (Read-Host 'พิมพ์ชื่อห้องที่จะทดสอบ').Trim()
if ($room -notin @('Windows', 'iOS', 'Android', 'Linux')) {
    Write-Host 'ชื่อห้องไม่ถูกต้อง ยกเลิกโดยไม่ส่งคำสั่ง' -ForegroundColor Red
    Read-Host 'กด Enter เพื่อปิดหน้าต่าง'
    exit 2
}

$securePassword = Read-Host 'รหัสผ่าน admin ของลำโพง (พิมพ์แบบซ่อน)' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $env:SPEAKER_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    & $pythonCommand.Source $scriptPath --test-speaker $room
    $exitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:SPEAKER_PASSWORD -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

Write-Host ''
Read-Host 'กด Enter เพื่อปิดหน้าต่าง'
exit $exitCode
