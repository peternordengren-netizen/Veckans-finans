# Skapar (eller ersätter) de schemalagda uppgifterna och skrivbordsgenvägen för Veckans finans.
#
# - VeckansFinansServer: vid inloggning, dolt (conhost --headless), kör scripts\serve.ps1.
#   Ingen tidsgräns, startas om tre gånger med en minuts mellanrum om den kraschar.
# - VeckansFinansVeckosammanfattning: måndagar 07:30, kör scripts\run_weekly.ps1.
#   Väcker datorn (kräver nätström – väckningstimers är avstängda på batteri), körs i
#   efterhand om datorn var avstängd, högst 2 timmar. Startas också fem minuter efter inloggning
#   och upplåsning, så att en missad måndag tas igen (skriptet gör inget om veckan redan finns).
# Båda körs som den inloggade användaren, bara när hen är inloggad, utan förhöjd behörighet.
# - Skrivbordsgenvägen "Veckans finans" kör scripts\open_site.ps1 dolt.
#
# Körs manuellt: powershell -NoProfile -File scripts\install_tasks.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Conhost = Join-Path $env:WINDIR "System32\conhost.exe"
$Ps = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$User = "$env:USERDOMAIN\$env:USERNAME"
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited

function HiddenAction([string]$Script) {
    New-ScheduledTaskAction -Execute $Conhost -WorkingDirectory $Root `
        -Argument "--headless `"$Ps`" -NoProfile -File `"$(Join-Path $Root $Script)`""
}

$serverSettings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "VeckansFinansServer" -Force `
    -Description "Veckans finans: lokal sida på http://localhost:4321/veckans-finans/ (astro preview)." `
    -Action (HiddenAction "scripts\serve.ps1") `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $User) `
    -Principal $Principal -Settings $serverSettings | Out-Null

# Måndag 07:30 lokal tid. New-ScheduledTaskTrigger sparar starttiden med dagens UTC-förskjutning
# (t.ex. +02:00 sommartid), och då flyttas körningen till 06:30 när vintertiden börjar. Utan
# förskjutning tolkas tiden alltid som lokal tid.
$weekly = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At "07:30"
$weekly.StartBoundary = (Get-Date "07:30").ToString("yyyy-MM-dd'T'HH:mm:ss")

# Inloggning och upplåsning, fem minuter fördröjt: tar igen en missad måndagskörning (t.ex. när
# datorn låg i viloläge till disk). run_weekly.ps1 avslutar direkt om veckan redan finns.
$atLogon = New-ScheduledTaskTrigger -AtLogOn -User $User
$atLogon.Delay = "PT5M"
$unlockClass = Get-CimClass -Namespace "Root/Microsoft/Windows/TaskScheduler" -ClassName "MSFT_TaskSessionStateChangeTrigger"
$atUnlock = New-CimInstance -CimClass $unlockClass -ClientOnly
$atUnlock.StateChange = 8  # TASK_SESSION_UNLOCK
$atUnlock.UserId = $User
$atUnlock.Delay = "PT5M"
$atUnlock.Enabled = $true

$weeklySettings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "VeckansFinansVeckosammanfattning" -Force `
    -Description "Veckans finans: /sammanfatta-veckan för förra veckan med Claude Code (dontAsk), bygger sedan om sidan. Loggar i logs\weekly\." `
    -Action (HiddenAction "scripts\run_weekly.ps1") `
    -Trigger @($weekly, $atLogon, $atUnlock) `
    -Principal $Principal -Settings $weeklySettings | Out-Null

$shell = New-Object -ComObject WScript.Shell
$lnk = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath("Desktop")) "Veckans finans.lnk"))
$lnk.TargetPath = $Conhost
$lnk.Arguments = "--headless `"$Ps`" -NoProfile -File `"$(Join-Path $Root 'scripts\open_site.ps1')`""
$lnk.WorkingDirectory = $Root
$lnk.IconLocation = "$env:WINDIR\System32\shell32.dll,13"
$lnk.Description = "Öppna Veckans finans (startar den lokala servern vid behov)"
$lnk.Save()

Get-ScheduledTask -TaskName "VeckansFinans*" | Select-Object TaskName, State
