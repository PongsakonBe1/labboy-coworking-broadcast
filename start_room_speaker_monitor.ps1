$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'room_speaker_monitor.py'

Write-Host 'K-ROOM Room Speaker Monitor'
Write-Host 'LIVE MODE: room-end events can play audio on the speakers.'

if (-not (Test-Path -LiteralPath $scriptPath)) {
    Write-Host "Python script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

$pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
}
if (-not $pythonCommand) {
    Write-Host 'Python was not found. Install Python and try again.' -ForegroundColor Red
    exit 1
}

$securePassword = Read-Host 'Speaker admin password (input is hidden)' -AsSecureString
$passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
$exitCode = 1
try {
    $env:SPEAKER_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    $env:SCHEDULE_URL = 'https://k-room.icit.kmutnb.ac.th/web/reserve/calendar'
    & $pythonCommand.Source $scriptPath --live
    $exitCode = $LASTEXITCODE
}
catch {
    Write-Host "Startup error: $_" -ForegroundColor Red
    $exitCode = 1
}
finally {
    Remove-Item Env:SPEAKER_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:SCHEDULE_URL -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
}

Write-Host ''
Write-Host 'Monitor stopped.'
exit $exitCode
