# Skapar dagens morgonrapport (scripts/morning.py, utan Claude) och bygger om sidan.
#
# Körs av den schemalagda uppgiften VeckansFinansMorgonrapport vardagar 08:10, samt fem
# minuter efter inloggning och upplåsning för att ta igen en missad morgon.
# - Ingen handelsdag (helg eller börsstängt): morning.py avslutar utan fil.
# - Finns dagens rapport redan avslutas skriptet direkt, utan att skriva i loggen.
# - Högst två försök per dag (räknas i loggen), så att ett fel inte ger en ny hämtning
#   från källorna vid varje upplåsning.
# - Efter rapporten sparas Yahoos konsensus (scripts/consensus.py --backup).
# - Logg i logs/morning/<datum>.log, bygget i logs/morning/<datum>-build.log.
#
# Manuellt: powershell -NoProfile -File scripts\run_morning.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs\morning"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Set-Location $Root
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$Today = Get-Date -Format "yyyy-MM-dd"
$Report = Join-Path $Root "data\morning\$Today.json"
$RunLog = Join-Path $LogDir "$Today.log"
if (Test-Path $Report) {
    Write-Output "data\morning\$Today.json finns redan - inget att göra."
    exit 0
}
$MaxAttempts = 2
$attempts = if (Test-Path $RunLog) { @(Select-String -Path $RunLog -SimpleMatch "Startar morning.py").Count } else { 0 }
if ($attempts -ge $MaxAttempts) {
    Write-Output "Redan $attempts försök i dag - avbryter. Se $RunLog."
    exit 0
}

function Log([string]$Text) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text
    Add-Content -Path $RunLog -Value $line -Encoding UTF8
    Write-Output $line
}

Log "Startar morning.py"
# Via cmd så att stderr (t.ex. yfinance-varningar) inte blir avbrytande PowerShell-fel.
& cmd.exe /c ".venv\Scripts\python.exe scripts\morning.py 2>&1" | ForEach-Object { Log "  $_" }
$code = $LASTEXITCODE
Log "morning.py: exit $code"

# Yahoos konsensus sparas varje morgon (och säkerhetskopieras), så att förväntan finns kvar
# efter att bolaget rapporterat. Fel här stoppar inte bygget.
if (Test-Path $Report) {
    & cmd.exe /c ".venv\Scripts\python.exe scripts\consensus.py --backup 2>&1" |
        Where-Object { $_ -match '^(Konsensus|Säkerhetskopia|Ingen|Konsensusfilen)' } | ForEach-Object { Log "  $_" }
    Log "consensus.py: exit $LASTEXITCODE"
}

if (Test-Path $Report) {
    $BuildLog = Join-Path $LogDir "$Today-build.log"
    & cmd.exe /c "npm run build > `"$BuildLog`" 2>&1"
    Log "npm run build: exit $LASTEXITCODE (logg: $BuildLog)"
}
Log "Klart"
