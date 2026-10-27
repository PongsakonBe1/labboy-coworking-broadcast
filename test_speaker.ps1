$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'room_speaker_monitor.py'
$exitCode = 1
$passwordPointer = [IntPtr]::Zero

Write-Host 'One-shot speaker test. The selected speaker will play audio once.'
Write-Host 'The console will remain open so errors can be read.'

try {
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Missing script: $scriptPath"
    }

    $pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    }
    if (-not $pythonCommand) {
        throw 'Python was not found in PATH.'
    }

    Write-Host ''
    Write-Host 'Rooms: Windows, iOS, Android, Linux'
    $room = (Read-Host 'Type the room to test').Trim()
    if ($room -notin @('Windows', 'iOS', 'Android', 'Linux')) {
        throw 'Invalid room name. No command was sent.'
    }

    $securePassword = Read-Host 'Speaker admin password (input is hidden)' -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    $env:SPEAKER_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)

    & $pythonCommand.Source $scriptPath --test-speaker $room
    $exitCode = $LASTEXITCODE
}
catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    $exitCode = 1
}
finally {
    Remove-Item Env:SPEAKER_PASSWORD -ErrorAction SilentlyContinue
    if ($passwordPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }
}

Write-Host ''
Read-Host 'Press Enter to finish this test'
exit $exitCode
