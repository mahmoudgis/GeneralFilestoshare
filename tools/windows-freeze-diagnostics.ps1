<#
.SYNOPSIS
    Read-only diagnostics collector for Windows freeze / USB bus collapse investigation.

.DESCRIPTION
    Collects power, USB, storage, hardware (WHEA) and application event data, device
    inventory, power-plan settings and health status, then performs local correlation
    analysis and writes a paste-ready summary.

    THIS SCRIPT IS STRICTLY READ-ONLY. It never changes a driver, registry value,
    power setting, device state or service. The only files it creates are its own
    report files under the output folder.

.NOTES
    Run in an elevated PowerShell (Run as Administrator).
    Windows PowerShell 5.1 or PowerShell 7+.
#>

[CmdletBinding()]
param(
    [int]    $Days                     = 30,
    [int]    $WheaDays                 = 60,
    [int]    $CorrelationWindowSeconds = 180,
    [int]    $AppCorrelationMinutes    = 15,
    [int]    $EnergyDurationSeconds    = 60,
    [switch] $SkipEnergyReport,
    [string] $OutputRoot               = "$env:USERPROFILE\Desktop"
)

$ErrorActionPreference = 'Continue'
$ProgressPreference    = 'SilentlyContinue'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Warning 'Not running as Administrator. Security log, some WMI classes and powercfg /energy will be unavailable.'
    Write-Warning 'Close this window and re-run PowerShell via "Run as administrator" for a complete collection.'
}

$stamp     = Get-Date -Format 'yyyyMMdd_HHmmss'
$outDir    = Join-Path $OutputRoot "FreezeDiag_$stamp"
$rawDir    = Join-Path $outDir 'raw'
$null      = New-Item -ItemType Directory -Path $rawDir -Force
$summary   = Join-Path $outDir 'ANALYSIS-SUMMARY.txt'
$since     = (Get-Date).AddDays(-$Days)
$sinceWhea = (Get-Date).AddDays(-$WheaDays)

$enc = 'UTF8'

function Write-Sum {
    param([string]$Text = '')
    $Text | Out-File -FilePath $summary -Append -Encoding $enc
    Write-Host $Text
}

function Save-Raw {
    param([string]$Name, $Content)
    $path = Join-Path $rawDir $Name
    if ($null -eq $Content) { 'No data returned.' | Out-File $path -Encoding $enc }
    else { $Content | Out-File $path -Encoding $enc -Width 4000 }
}

function Step {
    param([string]$Label)
    Write-Host ''
    Write-Host "==> $Label" -ForegroundColor Cyan
}

Write-Host ''
Write-Host "Output folder: $outDir" -ForegroundColor Green
Write-Host "Event window : last $Days day(s) (WHEA: last $WheaDays day(s))" -ForegroundColor Green

Write-Sum "WINDOWS FREEZE / USB BUS DIAGNOSTICS"
Write-Sum "Generated      : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')"
Write-Sum "Computer       : $env:COMPUTERNAME"
Write-Sum "Elevated       : $isAdmin"
Write-Sum "Event window   : $($since.ToString('yyyy-MM-dd HH:mm')) -> now"
Write-Sum ("=" * 78)
Write-Sum

# ---------------------------------------------------------------------------
# 0. Bulk event pulls (done once, reused by every later section)
# ---------------------------------------------------------------------------

Step 'Reading System event log (this can take a minute)'

$powerIds = 41, 6008, 1001, 6005, 6006, 6013, 42, 107, 109, 187

$powerEvents = @(Get-WinEvent -FilterHashtable @{
    LogName   = 'System'
    Id        = $powerIds
    StartTime = $since
} -ErrorAction SilentlyContinue)

# Level 1=Critical 2=Error 3=Warning
$sysProblems = @(Get-WinEvent -FilterHashtable @{
    LogName   = 'System'
    Level     = 1, 2, 3
    StartTime = $since
} -ErrorAction SilentlyContinue)

$busRegex = 'USB|UASP|usbstor|usbhub|usbxhci|disk|Ntfs|storahci|stornvme|iaStor|volmgr|volsnap|Kernel-PnP|Kernel-Power|Kernel-Processor|nvlddmkm|igfx|Display'

$busEvents = @($sysProblems | Where-Object { $_.ProviderName -match $busRegex })

Write-Host ("  power/shutdown events : {0}" -f $powerEvents.Count)
Write-Host ("  system warn/err/crit  : {0}" -f $sysProblems.Count)
Write-Host ("  bus/storage related   : {0}" -f $busEvents.Count)

# ---------------------------------------------------------------------------
# 1. Critical power events
# ---------------------------------------------------------------------------

Step '1/11  Critical power events (41 / 6008 / 1001)'

$critical = @($powerEvents | Where-Object { $_.Id -in 41, 6008, 1001 } |
              Sort-Object TimeCreated -Descending)

Save-Raw '01-power-critical.txt' ($critical |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String)

Save-Raw '01b-power-all-ids.txt' ($powerEvents | Sort-Object TimeCreated -Descending |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String)

# Decode Kernel-Power 41 payload (BugcheckCode / PowerButtonTimestamp)
function Get-Kp41Detail {
    param($Event)
    $d = [ordered]@{
        BugcheckCode         = $null
        BugcheckParameter1   = $null
        PowerButtonTimestamp = $null
    }
    try {
        $x = [xml]$Event.ToXml()
        foreach ($node in $x.Event.EventData.Data) {
            if ($d.Contains($node.Name)) { $d[$node.Name] = $node.'#text' }
        }
    } catch { }
    [pscustomobject]$d
}

$kp41 = @($critical | Where-Object { $_.Id -eq 41 } | ForEach-Object {
    $det = Get-Kp41Detail $_
    [pscustomobject]@{
        TimeCreated          = $_.TimeCreated
        BugcheckCode         = $det.BugcheckCode
        BugcheckHex          = if ($det.BugcheckCode) { '0x{0:X}' -f [int]$det.BugcheckCode } else { '' }
        PowerButtonTimestamp = $det.PowerButtonTimestamp
        Interpretation       = if ([string]::IsNullOrEmpty($det.BugcheckCode)) { 'unknown' }
                               elseif ([int]$det.BugcheckCode -eq 0) {
                                   if ($det.PowerButtonTimestamp -and [long]$det.PowerButtonTimestamp -ne 0) {
                                       'Power button held / forced off (no bugcheck)'
                                   } else {
                                       'Power loss or hard hang - NO bluescreen recorded'
                                   }
                               }
                               else { 'BLUESCREEN (bugcheck) preceded the restart' }
    }
})

Save-Raw '01c-kernelpower41-decoded.txt' ($kp41 | Format-List | Out-String)

Write-Sum 'SECTION 1 - CRITICAL POWER EVENTS'
Write-Sum ('-' * 78)
Write-Sum ("Kernel-Power 41 (unexpected shutdown)      : {0}" -f @($critical | Where-Object Id -eq 41).Count)
Write-Sum ("EventLog 6008 (previous shutdown unexpected): {0}" -f @($critical | Where-Object Id -eq 6008).Count)
Write-Sum ("Id 1001 (bugcheck / error reporting)       : {0}" -f @($critical | Where-Object Id -eq 1001).Count)
Write-Sum

if ($kp41.Count -gt 0) {
    Write-Sum 'Kernel-Power 41 breakdown (question C):'
    foreach ($k in $kp41) {
        Write-Sum ("  {0}  BugcheckCode={1} ({2})  PowerButtonTS={3}  => {4}" -f `
            $k.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $k.BugcheckCode, $k.BugcheckHex,
            $k.PowerButtonTimestamp, $k.Interpretation)
    }
} else {
    Write-Sum 'No Kernel-Power 41 events in the window.'
    Write-Sum 'NOTE: a freeze where you held the power button still logs 41 on the NEXT boot;'
    Write-Sum '      zero 41 events means the machine was always shut down cleanly afterwards,'
    Write-Sum '      which points to a soft hang rather than a power/rail failure.'
}
Write-Sum

# ---------------------------------------------------------------------------
# 2. USB / disk / PnP events
# ---------------------------------------------------------------------------

Step '2/11  USB, storage and PnP errors/warnings'

Save-Raw '02-usb-disk-pnp.txt' ($busEvents | Sort-Object TimeCreated -Descending |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String)

$busByProvider = $busEvents | Group-Object ProviderName |
                 Sort-Object Count -Descending |
                 Select-Object Count, Name

$busByIdProv = $busEvents | Group-Object ProviderName, Id |
               Sort-Object Count -Descending |
               Select-Object Count, Name

Save-Raw '02b-usb-disk-histogram.txt' (($busByProvider | Format-Table -AutoSize | Out-String) + "`n" +
                                       ($busByIdProv   | Format-Table -AutoSize | Out-String))

Write-Sum 'SECTION 2 - USB / DISK / PnP EVENTS (top providers)'
Write-Sum ('-' * 78)
Write-Sum (($busByProvider | Select-Object -First 20 | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum
Write-Sum 'Most frequent provider+id pairs:'
Write-Sum (($busByIdProv | Select-Object -First 20 | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum

# Surprise-removal signature for the external drive
$surprise = @($busEvents | Where-Object {
    $_.Id -in 157, 51, 129, 153, 11, 15, 219, 225 -or $_.Message -match 'surprise removal|was surprise removed|not ready for access|reset to device'
} | Sort-Object TimeCreated -Descending)

Save-Raw '02c-surprise-removal.txt' ($surprise |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String)

Write-Sum ("Surprise-removal / device-reset signatures found: {0}" -f $surprise.Count)
if ($surprise.Count -gt 0) {
    Write-Sum 'Most recent 15:'
    foreach ($s in ($surprise | Select-Object -First 15)) {
        $line = ($s.Message -split "`r?`n")[0]
        if ($line.Length -gt 120) { $line = $line.Substring(0,120) + '...' }
        Write-Sum ("  {0}  Id={1,-4} {2,-38} {3}" -f `
            $s.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $s.Id, $s.ProviderName, $line)
    }
}
Write-Sum

# ---------------------------------------------------------------------------
# 3. WHEA hardware errors
# ---------------------------------------------------------------------------

Step '3/11  WHEA hardware error records'

$whea = @(Get-WinEvent -FilterHashtable @{
    LogName      = 'System'
    ProviderName = 'Microsoft-Windows-WHEA-Logger'
    StartTime    = $sinceWhea
} -ErrorAction SilentlyContinue | Sort-Object TimeCreated -Descending)

Save-Raw '03-whea.txt' ($whea | Select-Object TimeCreated, Id, LevelDisplayName, Message | Format-List | Out-String)

Write-Sum 'SECTION 3 - WHEA HARDWARE ERRORS'
Write-Sum ('-' * 78)
Write-Sum ("WHEA records in last $WheaDays days: {0}" -f $whea.Count)
foreach ($w in ($whea | Select-Object -First 15)) {
    $line = ($w.Message -split "`r?`n")[0]
    Write-Sum ("  {0}  Id={1,-4} {2}" -f $w.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $w.Id, $line)
}
Write-Sum

# ---------------------------------------------------------------------------
# 4. Application errors (ArcGIS and others)
# ---------------------------------------------------------------------------

Step '4/11  Application log errors'

$appEvents = @(Get-WinEvent -FilterHashtable @{
    LogName   = 'Application'
    Level     = 1, 2
    StartTime = $since
} -ErrorAction SilentlyContinue | Sort-Object TimeCreated -Descending)

Save-Raw '04-application-errors.txt' ($appEvents | Select-Object -First 200 |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, Message | Format-List | Out-String)

$arcRegex = 'ArcGIS|ArcMap|ArcSOC|ArcCatalog|Esri|ArcGISPro'
$arcEvents = @($appEvents | Where-Object { $_.ProviderName -match $arcRegex -or $_.Message -match $arcRegex })

Save-Raw '04b-arcgis-events.txt' ($arcEvents |
    Select-Object TimeCreated, Id, ProviderName, Message | Format-List | Out-String)

Write-Sum 'SECTION 4 - APPLICATION ERRORS'
Write-Sum ('-' * 78)
Write-Sum ("Application errors/critical in window: {0}" -f $appEvents.Count)
Write-Sum ("Of which ArcGIS/Esri related        : {0}" -f $arcEvents.Count)
Write-Sum
Write-Sum 'Top application error sources:'
Write-Sum (($appEvents | Group-Object ProviderName | Sort-Object Count -Descending |
            Select-Object -First 15 Count, Name | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum

# Is ArcGIS installed / currently running (context only)
$arcInstalled = @(Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                                'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall' `
                  -ErrorAction SilentlyContinue |
                  ForEach-Object { $_.GetValue('DisplayName') } |
                  Where-Object { $_ -match $arcRegex })

$arcRunning = @(Get-Process -ErrorAction SilentlyContinue |
                Where-Object { $_.ProcessName -match 'ArcGISPro|ArcMap|ArcSOC|ArcCatalog' } |
                Select-Object ProcessName, Id, StartTime, `
                    @{n='WorkingSetMB';e={[math]::Round($_.WorkingSet64/1MB,0)}})

Save-Raw '04c-arcgis-context.txt' (($arcInstalled | Out-String) + "`n" + ($arcRunning | Format-Table -AutoSize | Out-String))
Write-Sum ("ArcGIS products installed: {0}" -f ($(if ($arcInstalled.Count) { $arcInstalled -join '; ' } else { 'none detected' })))
Write-Sum ("ArcGIS processes running now: {0}" -f ($(if ($arcRunning.Count) { ($arcRunning.ProcessName -join ', ') } else { 'none' })))
Write-Sum

# ---------------------------------------------------------------------------
# 5. Crash dumps
# ---------------------------------------------------------------------------

Step '5/11  Crash dump files'

$mini = @(Get-ChildItem 'C:\Windows\Minidump' -ErrorAction SilentlyContinue |
          Select-Object Name, LastWriteTime, Length | Sort-Object LastWriteTime -Descending)
$memDmpExists = Test-Path 'C:\Windows\MEMORY.DMP'
$memDmp = if ($memDmpExists) { Get-Item 'C:\Windows\MEMORY.DMP' | Select-Object FullName, LastWriteTime, Length } else { $null }
$liveKernel = @(Get-ChildItem 'C:\Windows\LiveKernelReports' -Recurse -File -ErrorAction SilentlyContinue |
                Select-Object FullName, LastWriteTime, Length | Sort-Object LastWriteTime -Descending)

$crashCfg = Get-CimInstance Win32_OSRecoveryConfiguration -ErrorAction SilentlyContinue |
            Select-Object DebugInfoType, DebugFilePath, MiniDumpDirectory, AutoReboot, WriteDebugInfo

Save-Raw '05-dumps.txt' (($mini | Format-Table -AutoSize | Out-String) + "`n" +
                          "MEMORY.DMP exists: $memDmpExists`n" + ($memDmp | Format-List | Out-String) + "`n" +
                          "LiveKernelReports:`n" + ($liveKernel | Format-Table -AutoSize | Out-String) + "`n" +
                          "Crash dump configuration:`n" + ($crashCfg | Format-List | Out-String))

Write-Sum 'SECTION 5 - CRASH DUMPS'
Write-Sum ('-' * 78)
Write-Sum ("Minidumps           : {0}" -f $mini.Count)
foreach ($m in ($mini | Select-Object -First 15)) {
    Write-Sum ("  {0}  {1}  {2} KB" -f $m.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'), $m.Name, [math]::Round($m.Length/1KB))
}
Write-Sum ("MEMORY.DMP present  : {0}" -f $memDmpExists)
Write-Sum ("LiveKernelReports   : {0}" -f $liveKernel.Count)
Write-Sum ("Dump configuration  : {0}" -f ($crashCfg | Out-String).Trim())
Write-Sum

# ---------------------------------------------------------------------------
# 6. Machine, BIOS, memory
# ---------------------------------------------------------------------------

Step '6/11  System, BIOS and memory inventory'

$cs   = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue |
        Select-Object Manufacturer, Model, SystemFamily, TotalPhysicalMemory, NumberOfProcessors
$bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue |
        Select-Object SMBIOSBIOSVersion, Manufacturer, ReleaseDate, SerialNumber
$os   = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue |
        Select-Object Caption, Version, BuildNumber, OSArchitecture, LastBootUpTime, InstallDate
$cpu  = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue |
        Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed
$mem  = Get-CimInstance Win32_PhysicalMemory -ErrorAction SilentlyContinue |
        Select-Object BankLabel, DeviceLocator, Capacity, Speed, ConfiguredClockSpeed, Manufacturer, PartNumber
$gpu  = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue |
        Select-Object Name, DriverVersion, DriverDate, AdapterRAM, VideoProcessor, Status

Save-Raw '06-system-inventory.txt' (
    "ComputerSystem:`n"  + ($cs   | Format-List | Out-String) +
    "BIOS:`n"            + ($bios | Format-List | Out-String) +
    "OS:`n"              + ($os   | Format-List | Out-String) +
    "CPU:`n"             + ($cpu  | Format-List | Out-String) +
    "Physical memory:`n" + ($mem  | Format-Table -AutoSize | Out-String) +
    "Video:`n"           + ($gpu  | Format-List | Out-String))

Write-Sum 'SECTION 6 - SYSTEM INVENTORY'
Write-Sum ('-' * 78)
Write-Sum ("Model        : {0} {1} ({2})" -f $cs.Manufacturer, $cs.Model, $cs.SystemFamily)
Write-Sum ("RAM total    : {0} GB" -f [math]::Round($cs.TotalPhysicalMemory/1GB,1))
Write-Sum ("BIOS         : {0}  released {1}" -f $bios.SMBIOSBIOSVersion, $(if($bios.ReleaseDate){$bios.ReleaseDate.ToString('yyyy-MM-dd')}))
Write-Sum ("OS           : {0} build {1}" -f $os.Caption, $os.BuildNumber)
Write-Sum ("Last boot    : {0}" -f $os.LastBootUpTime)
Write-Sum ("CPU          : {0}" -f ($cpu.Name -join '; '))
Write-Sum ("GPU driver   : {0} / {1} ({2})" -f ($gpu.Name -join ', '), ($gpu.DriverVersion -join ', '), $(if($gpu.DriverDate){($gpu.DriverDate | ForEach-Object { $_.ToString('yyyy-MM-dd') }) -join ', '}))
Write-Sum 'Memory modules:'
Write-Sum (($mem | Format-Table BankLabel, DeviceLocator, @{n='GB';e={[math]::Round($_.Capacity/1GB,1)}}, Speed, ConfiguredClockSpeed, Manufacturer, PartNumber -AutoSize | Out-String).TrimEnd())
Write-Sum

# ---------------------------------------------------------------------------
# 7. Disk health
# ---------------------------------------------------------------------------

Step '7/11  Disk health and reliability counters'

$pdisk = @(Get-PhysicalDisk -ErrorAction SilentlyContinue |
           Select-Object DeviceId, FriendlyName, MediaType, BusType, `
               @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}, HealthStatus, OperationalStatus)
$disk  = @(Get-Disk -ErrorAction SilentlyContinue |
           Select-Object Number, FriendlyName, BusType, `
               @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}, HealthStatus, OperationalStatus, PartitionStyle)
$vol   = @(Get-Volume -ErrorAction SilentlyContinue |
           Select-Object DriveLetter, FileSystemLabel, FileSystem, HealthStatus, `
               @{n='SizeGB';e={[math]::Round($_.Size/1GB,1)}}, `
               @{n='FreeGB';e={[math]::Round($_.SizeRemaining/1GB,1)}})

$rel = foreach ($p in (Get-PhysicalDisk -ErrorAction SilentlyContinue)) {
    $c = $p | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue
    if ($c) {
        [pscustomobject]@{
            Disk              = $p.FriendlyName
            Temperature       = $c.Temperature
            PowerOnHours      = $c.PowerOnHours
            ReadErrorsTotal   = $c.ReadErrorsTotal
            WriteErrorsTotal  = $c.WriteErrorsTotal
            Wear              = $c.Wear
            StartStopCycles   = $c.StartStopCycleCount
        }
    }
}

Save-Raw '07-disks.txt' (
    "PhysicalDisk:`n" + ($pdisk | Format-Table -AutoSize | Out-String) +
    "Disk:`n"         + ($disk  | Format-Table -AutoSize | Out-String) +
    "Volume:`n"       + ($vol   | Format-Table -AutoSize | Out-String) +
    "Reliability:`n"  + ($rel   | Format-Table -AutoSize | Out-String))

Write-Sum 'SECTION 7 - DISKS'
Write-Sum ('-' * 78)
Write-Sum (($pdisk | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum (($disk  | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum 'Reliability counters:'
Write-Sum (($rel | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum

# ---------------------------------------------------------------------------
# 8. USB devices and per-device power saving
# ---------------------------------------------------------------------------

Step '8/11  USB device inventory and power-saving flags'

$usbDev = @(Get-PnpDevice -Class USB -ErrorAction SilentlyContinue |
            Select-Object Status, FriendlyName, InstanceId | Sort-Object Status, FriendlyName)
$usbCtrl = @(Get-CimInstance Win32_USBController -ErrorAction SilentlyContinue |
             Select-Object Name, DeviceID, Status, ConfigManagerErrorCode)
$usbHub  = @(Get-CimInstance Win32_USBHub -ErrorAction SilentlyContinue |
             Select-Object Name, DeviceID, Status)

$pwrEnable = @(Get-CimInstance -Namespace root\WMI -ClassName MSPower_DeviceEnable -ErrorAction SilentlyContinue |
               Select-Object InstanceName, Enable)

# Which devices are allowed to be powered down by Windows (Enable = $true)
$pwrOn = @($pwrEnable | Where-Object { $_.Enable -eq $true })

Save-Raw '08-usb-devices.txt' (
    "PnP USB class devices:`n" + ($usbDev  | Format-Table -AutoSize -Wrap | Out-String) +
    "USB controllers:`n"       + ($usbCtrl | Format-Table -AutoSize -Wrap | Out-String) +
    "USB hubs:`n"              + ($usbHub  | Format-Table -AutoSize -Wrap | Out-String) +
    "MSPower_DeviceEnable:`n"  + ($pwrEnable | Format-Table -AutoSize -Wrap | Out-String))

Write-Sum 'SECTION 8 - USB INVENTORY'
Write-Sum ('-' * 78)
Write-Sum ("USB class devices           : {0}" -f $usbDev.Count)
Write-Sum ("USB controllers             : {0}" -f $usbCtrl.Count)
Write-Sum ("USB hubs                    : {0}" -f $usbHub.Count)
Write-Sum ("Devices Windows may power off (Enable=True): {0} of {1}" -f $pwrOn.Count, $pwrEnable.Count)
Write-Sum
Write-Sum 'USB controllers:'
Write-Sum (($usbCtrl | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum

# ---------------------------------------------------------------------------
# 9. Problem devices
# ---------------------------------------------------------------------------

Step '9/11  Devices not in OK state'

$badDev = @(Get-PnpDevice -ErrorAction SilentlyContinue |
            Where-Object { $_.Status -ne 'OK' } |
            Select-Object Status, Class, FriendlyName, InstanceId, Problem, ProblemDescription |
            Sort-Object Status, Class)

Save-Raw '09-problem-devices.txt' ($badDev | Format-Table -AutoSize -Wrap | Out-String)

Write-Sum 'SECTION 9 - PROBLEM DEVICES'
Write-Sum ('-' * 78)
Write-Sum ("Devices not OK (includes normal 'Unknown' for unplugged hardware): {0}" -f $badDev.Count)
Write-Sum (($badDev | Where-Object { $_.Status -eq 'Error' } | Format-Table -AutoSize | Out-String).TrimEnd())
Write-Sum

# ---------------------------------------------------------------------------
# 10. Power plan
# ---------------------------------------------------------------------------

Step '10/11  Active power plan'

$scheme    = (powercfg /getactivescheme) 2>&1 | Out-String
$subProc   = (powercfg /query SCHEME_CURRENT SUB_PROCESSOR) 2>&1 | Out-String
$subUsb    = (powercfg /query SCHEME_CURRENT 2a737441-1930-4402-8d77-b2bebba308a3) 2>&1 | Out-String
$subDisk   = (powercfg /query SCHEME_CURRENT SUB_DISK) 2>&1 | Out-String
$sleepDiag = (powercfg /a) 2>&1 | Out-String
$devWake   = (powercfg /devicequery wake_armed) 2>&1 | Out-String

Save-Raw '10-powerplan.txt' (
    "Active scheme:`n$scheme`n" +
    "SUB_PROCESSOR:`n$subProc`n" +
    "USB settings subgroup:`n$subUsb`n" +
    "SUB_DISK:`n$subDisk`n" +
    "Available sleep states:`n$sleepDiag`n" +
    "Wake-armed devices:`n$devWake")

# Extract USB selective suspend current value
$usbSuspend = 'not found'
if ($subUsb -match '(?s)USB selective suspend.*?Current AC Power Setting Index:\s*(0x[0-9a-fA-F]+)') {
    $usbSuspend = if ([convert]::ToInt32($Matches[1],16) -eq 1) { 'ENABLED' } else { 'disabled' }
}

Write-Sum 'SECTION 10 - POWER PLAN'
Write-Sum ('-' * 78)
Write-Sum $scheme.Trim()
Write-Sum ("USB selective suspend (AC): {0}" -f $usbSuspend)
Write-Sum

# ---------------------------------------------------------------------------
# 11. powercfg energy / battery reports
# ---------------------------------------------------------------------------

Step '11/11  Energy and battery reports'

if ($SkipEnergyReport) {
    Write-Sum 'SECTION 11 - ENERGY REPORT: skipped (-SkipEnergyReport).'
} elseif (-not $isAdmin) {
    Write-Sum 'SECTION 11 - ENERGY REPORT: skipped, requires Administrator.'
} else {
    $energyPath  = Join-Path $outDir 'energy-report.html'
    $batteryPath = Join-Path $outDir 'battery-report.html'
    Write-Host "  tracing for $EnergyDurationSeconds seconds..." -ForegroundColor Yellow
    $null = (powercfg /energy /output "$energyPath" /duration $EnergyDurationSeconds) 2>&1
    $null = (powercfg /batteryreport /output "$batteryPath") 2>&1

    Write-Sum 'SECTION 11 - ENERGY REPORT'
    Write-Sum ('-' * 78)
    Write-Sum ("energy-report.html written : {0}" -f (Test-Path $energyPath))
    Write-Sum ("battery-report.html written: {0} (expected to fail on a desktop - no battery)" -f (Test-Path $batteryPath))

    if (Test-Path $energyPath) {
        $html = Get-Content $energyPath -Raw
        $txt  = ($html -replace '<[^>]+>', ' ') -replace '\s{2,}', ' '
        $errCount  = ([regex]::Matches($html, 'class="?errorTitle')).Count
        $warnCount = ([regex]::Matches($html, 'class="?warnTitle')).Count
        Write-Sum ("Energy report: {0} error(s), {1} warning(s)" -f $errCount, $warnCount)
        Save-Raw '11-energy-report-text.txt' $txt
    }
}
Write-Sum

# ---------------------------------------------------------------------------
# ANALYSIS A/B: timeline and pre-freeze correlation
# ---------------------------------------------------------------------------

Step 'Correlation analysis'

Write-Sum ('=' * 78)
Write-Sum 'ANALYSIS A - TIMELINE OF STOP / DISCONNECT EVENTS'
Write-Sum ('=' * 78)

$anchors = @($critical | Sort-Object TimeCreated -Descending)

if ($anchors.Count -eq 0) {
    Write-Sum 'No 41 / 6008 / 1001 anchors in the window; timeline below is built from bus events only.'
    foreach ($b in ($busEvents | Sort-Object TimeCreated -Descending | Select-Object -First 40)) {
        $line = ($b.Message -split "`r?`n")[0]
        if ($line.Length -gt 110) { $line = $line.Substring(0,110) + '...' }
        Write-Sum ("  {0}  {1,-34} Id={2,-4} {3}" -f `
            $b.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $b.ProviderName, $b.Id, $line)
    }
} else {
    foreach ($a in $anchors) {
        Write-Sum
        Write-Sum ("### ANCHOR {0}  Id={1}  {2}" -f $a.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $a.Id, $a.ProviderName)
        if ($a.Id -eq 41) {
            $k = $kp41 | Where-Object { $_.TimeCreated -eq $a.TimeCreated } | Select-Object -First 1
            if ($k) { Write-Sum ("    BugcheckCode={0} => {1}" -f $k.BugcheckCode, $k.Interpretation) }
        }
        $winStart = $a.TimeCreated.AddSeconds(-$CorrelationWindowSeconds)
        $before = @($busEvents | Where-Object {
            $_.TimeCreated -ge $winStart -and $_.TimeCreated -le $a.TimeCreated
        } | Sort-Object TimeCreated)

        if ($before.Count -eq 0) {
            Write-Sum ("    No USB/disk/PnP event in the {0}s before this anchor." -f $CorrelationWindowSeconds)
        } else {
            Write-Sum ("    {0} bus/storage event(s) in the {1}s before:" -f $before.Count, $CorrelationWindowSeconds)
            foreach ($b in $before) {
                $delta = [int]($a.TimeCreated - $b.TimeCreated).TotalSeconds
                $line = ($b.Message -split "`r?`n")[0]
                if ($line.Length -gt 100) { $line = $line.Substring(0,100) + '...' }
                Write-Sum ("      -{0,4}s  {1,-32} Id={2,-4} {3}" -f $delta, $b.ProviderName, $b.Id, $line)
            }
        }

        # Application-layer context around the anchor
        $appNear = @($appEvents | Where-Object {
            $_.TimeCreated -ge $a.TimeCreated.AddMinutes(-$AppCorrelationMinutes) -and
            $_.TimeCreated -le $a.TimeCreated.AddMinutes($AppCorrelationMinutes)
        } | Sort-Object TimeCreated)
        if ($appNear.Count -gt 0) {
            Write-Sum ("    Application errors within +/-{0} min:" -f $AppCorrelationMinutes)
            foreach ($ap in ($appNear | Select-Object -First 10)) {
                Write-Sum ("      {0}  {1}  Id={2}" -f $ap.TimeCreated.ToString('HH:mm:ss'), $ap.ProviderName, $ap.Id)
            }
        }
    }
}
Write-Sum

Write-Sum ('=' * 78)
Write-Sum 'ANALYSIS B - DOES THE BUS FAIL FIRST?'
Write-Sum ('=' * 78)

$withBus = 0; $withoutBus = 0
foreach ($a in $anchors) {
    $winStart = $a.TimeCreated.AddSeconds(-$CorrelationWindowSeconds)
    $n = @($busEvents | Where-Object { $_.TimeCreated -ge $winStart -and $_.TimeCreated -lt $a.TimeCreated }).Count
    if ($n -gt 0) { $withBus++ } else { $withoutBus++ }
}
Write-Sum ("Anchors preceded by USB/disk/PnP events : {0}" -f $withBus)
Write-Sum ("Anchors with a clean {0}s lead-in       : {1}" -f $CorrelationWindowSeconds, $withoutBus)
Write-Sum
Write-Sum 'Reading:'
Write-Sum '  - Bus events consistently first  => the USB/storage bus is the initiator.'
Write-Sum '  - Nothing at all before the stop => instantaneous cut, i.e. power delivery or a hard hang.'
Write-Sum

Write-Sum ('=' * 78)
Write-Sum 'ANALYSIS C - BUGCHECK CLASSIFICATION'
Write-Sum ('=' * 78)
$bcZero    = @($kp41 | Where-Object { $_.BugcheckCode -eq '0' }).Count
$bcNonZero = @($kp41 | Where-Object { $_.BugcheckCode -and $_.BugcheckCode -ne '0' }).Count
Write-Sum ("41 events with BugcheckCode = 0    : {0}  (no bluescreen: power cut / forced off / hard hang)" -f $bcZero)
Write-Sum ("41 events with BugcheckCode <> 0   : {0}  (a real bluescreen occurred)" -f $bcNonZero)
Write-Sum ("Minidump files on disk             : {0}  (dumps confirm bugchecks)" -f $mini.Count)
Write-Sum

Write-Sum ('=' * 78)
Write-Sum 'ANALYSIS D - ArcGIS TEMPORAL CORRELATION'
Write-Sum ('=' * 78)
Write-Sum ("ArcGIS/Esri application errors in window: {0}" -f $arcEvents.Count)
if ($arcEvents.Count -gt 0) {
    foreach ($e in ($arcEvents | Select-Object -First 20)) {
        Write-Sum ("  {0}  {1}  Id={2}" -f $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss'), $e.ProviderName, $e.Id)
    }
}
$arcNearAnchor = 0
foreach ($a in $anchors) {
    $hit = @($arcEvents | Where-Object {
        $_.TimeCreated -ge $a.TimeCreated.AddMinutes(-60) -and $_.TimeCreated -le $a.TimeCreated
    }).Count
    if ($hit -gt 0) { $arcNearAnchor++ }
}
Write-Sum ("Anchors with an ArcGIS error in the hour before: {0} of {1}" -f $arcNearAnchor, $anchors.Count)
Write-Sum
Write-Sum 'Hour-of-day distribution of stop events:'
$byHour = $anchors | Group-Object { $_.TimeCreated.Hour } | Sort-Object { [int]$_.Name }
foreach ($h in $byHour) { Write-Sum ("  {0,2}:00  {1}" -f $h.Name, ('#' * $h.Count)) }
Write-Sum
Write-Sum 'Day-of-week distribution:'
$byDow = $anchors | Group-Object { $_.TimeCreated.DayOfWeek } | Sort-Object Count -Descending
foreach ($d in $byDow) { Write-Sum ("  {0,-10} {1}" -f $d.Name, $d.Count) }
Write-Sum

Write-Sum ('=' * 78)
Write-Sum 'END OF SUMMARY - send this file plus the raw folder for full analysis.'
Write-Sum ('=' * 78)

# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

Step 'Packaging'

$zip = Join-Path $OutputRoot "FreezeDiag_$stamp.zip"
try {
    Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $zip -Force -ErrorAction Stop
    Write-Host "ZIP : $zip" -ForegroundColor Green
} catch {
    Write-Warning "Could not create ZIP: $($_.Exception.Message)"
}

Write-Host ''
Write-Host 'DONE. Nothing on this system was modified.' -ForegroundColor Green
Write-Host "Summary : $summary" -ForegroundColor Green
Write-Host "Raw data: $rawDir" -ForegroundColor Green
