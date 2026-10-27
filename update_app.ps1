param(
    [switch]$CheckOnly,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'

function Get-LabBoyProcesses {
    param([Parameter(Mandatory=$true)][string]$AppDirectory)
    $appRoot = [IO.Path]::GetFullPath($AppDirectory).TrimEnd('\')
    $exePaths = @(
        (Join-Path $appRoot 'labboy_coworking_broadcast.exe'),
        (Join-Path $appRoot 'room_speaker_monitor.exe')
    )
    $scriptPaths = @(
        (Join-Path $appRoot 'labboy_coworking_broadcast.py'),
        (Join-Path $appRoot 'room_speaker_monitor.py')
    )
    $all = @(Get-CimInstance Win32_Process -Filter "Name='room_speaker_monitor.exe' OR Name='labboy_coworking_broadcast.exe' OR Name='python.exe' OR Name='pythonw.exe'")
    foreach ($item in $all) {
        $candidatePath = if ($item.ExecutablePath) { [IO.Path]::GetFullPath($item.ExecutablePath) } else { '' }
        $isOurExe = $candidatePath -and ($exePaths -contains $candidatePath)
        $isOurScript = $false
        if ($item.Name -in @('python.exe', 'pythonw.exe') -and $item.CommandLine) {
            foreach ($path in $scriptPaths) {
                if ($item.CommandLine -match ('(?:^|[\s"])' + [regex]::Escape($path) + '(?=$|[\s"])')) {
                    $isOurScript = $true
                }
            }
        }
        if ($isOurExe -or $isOurScript) { $item }
    }
}

function Stop-LabBoyProcesses {
    param([Parameter(Mandatory=$true)][string]$AppDirectory)
    $processes = @(Get-LabBoyProcesses -AppDirectory $AppDirectory)
    $ids = @($processes | ForEach-Object { [int]$_.ProcessId })
    # PyInstaller มีทั้ง bootloader และ child; หยุดจาก root ของกลุ่มที่ตรวจ path แล้ว.
    foreach ($item in $processes) {
        if ($ids -notcontains [int]$item.ParentProcessId) {
            & "$env:SystemRoot\System32\taskkill.exe" /PID ([string]$item.ProcessId) /T /F 2>&1 | Out-Null
        }
    }
    $deadline = (Get-Date).AddSeconds(10)
    do {
        $remaining = @(Get-LabBoyProcesses -AppDirectory $AppDirectory)
        if ($remaining.Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    } while ((Get-Date) -lt $deadline)
    throw 'ยังหยุดโปรแกรมเดิมไม่ได้ จึงยังไม่เปลี่ยนไฟล์ กรุณาปิดโปรแกรมแล้วลองใหม่'
}

function Install-LabBoyRelease {
    param([Parameter(Mandatory=$true)][string]$AppDirectory)
    $appRoot = [IO.Path]::GetFullPath($AppDirectory).TrimEnd('\')
    $release = Join-Path $appRoot 'build\release'
    $names = @('room_speaker_monitor.exe', 'labboy_coworking_broadcast.exe')
    # ตรวจไฟล์ทั้งหมดก่อนคัดลอก เพื่อไม่ทิ้งการติดตั้งที่มี executable เพียงไฟล์เดียว.
    foreach ($name in $names) {
        $source = Join-Path $release $name
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "ไม่พบไฟล์รุ่นใหม่: $name" }
        if ((Get-Item -LiteralPath $source).Length -eq 0) { throw "ไฟล์รุ่นใหม่ว่าง: $name" }
    }
    if (@(Get-LabBoyProcesses -AppDirectory $appRoot).Count -gt 0) {
        throw 'โปรแกรมยังทำงานอยู่ จึงยังไม่เปลี่ยนไฟล์'
    }
    $backup = Join-Path $appRoot ('build\update-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    $originals = @()
    foreach ($name in $names) {
        $target = Join-Path $appRoot $name
        if (Test-Path -LiteralPath $target -PathType Leaf) {
            Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name) -Force
            $originals += $name
        }
    }
    try {
        foreach ($name in $names) {
            $source = Join-Path $release $name
            $target = Join-Path $appRoot $name
            Copy-Item -LiteralPath $source -Destination $target -Force
            if ((Get-LabBoyFileHash -LiteralPath $source) -ne (Get-LabBoyFileHash -LiteralPath $target)) {
                throw "ตรวจไฟล์หลังอัปเดตไม่ผ่าน: $name"
            }
        }
    } catch {
        foreach ($name in $originals) {
            Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $appRoot $name) -Force
        }
        throw
    }
    return $backup
}

function Get-LabBoyFileHash {
    param([Parameter(Mandatory=$true)][string]$LiteralPath)
    $stream = [IO.File]::OpenRead($LiteralPath)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return [BitConverter]::ToString($sha.ComputeHash($stream))
    } finally {
        $stream.Dispose()
        $sha.Dispose()
    }
}

if ($LibraryOnly) { return }
$appRoot = $PSScriptRoot
if ($CheckOnly) {
    $processes = @(Get-LabBoyProcesses -AppDirectory $appRoot)
    [pscustomobject]@{
        RunningCount = $processes.Count
        Processes = @($processes | Select-Object Name, ProcessId)
        ReleaseReady = ((Test-Path -LiteralPath (Join-Path $appRoot 'build\release\room_speaker_monitor.exe')) -and
                        (Test-Path -LiteralPath (Join-Path $appRoot 'build\release\labboy_coworking_broadcast.exe')))
    } | ConvertTo-Json -Depth 4
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
try {
    foreach ($name in @('room_speaker_monitor.exe', 'labboy_coworking_broadcast.exe')) {
        $source = Join-Path $appRoot ('build\release\' + $name)
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "ไม่พบไฟล์รุ่นใหม่: $name" }
        if ((Get-Item -LiteralPath $source).Length -eq 0) { throw "ไฟล์รุ่นใหม่ว่าง: $name" }
    }
    $running = @(Get-LabBoyProcesses -AppDirectory $appRoot)
    $message = 'ต้องการอัปเดต LabBoy และเปิดโปรแกรมใหม่หรือไม่?' + [Environment]::NewLine + [Environment]::NewLine
    if ($running.Count -gt 0) {
        $message += 'พบส่วนของโปรแกรมยังทำงานอยู่ แม้หน้าต่างอาจปิดไปแล้ว ตัวอัปเดตจะหยุดเฉพาะ LabBoy ในโฟลเดอร์นี้' + [Environment]::NewLine + [Environment]::NewLine
    }
    $message += 'ระหว่างอัปเดตจะไม่มีการประกาศเสียงอัตโนมัติ และจะเริ่มต่อเมื่อเปิดโปรแกรมใหม่' + [Environment]::NewLine + 'รหัสผ่าน การตั้งค่า และประวัติเสียงจะคงอยู่'
    $answer = [Windows.Forms.MessageBox]::Show($message, 'อัปเดต LabBoy', [Windows.Forms.MessageBoxButtons]::YesNo, [Windows.Forms.MessageBoxIcon]::Question)
    if ($answer -ne [Windows.Forms.DialogResult]::Yes) { exit 2 }
    Stop-LabBoyProcesses -AppDirectory $appRoot
    $backup = Install-LabBoyRelease -AppDirectory $appRoot
    Write-Host 'Update completed. The previous executable files were backed up.'
    Start-Process -FilePath (Join-Path $appRoot 'labboy_coworking_broadcast.exe') -WorkingDirectory $appRoot
    exit 0
} catch {
    [Windows.Forms.MessageBox]::Show($_.Exception.Message, 'อัปเดตไม่สำเร็จ', [Windows.Forms.MessageBoxButtons]::OK, [Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    exit 1
}
