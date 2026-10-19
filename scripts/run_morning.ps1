# Morgonkörningen: morgonrapport (scripts/morning.py, utan Claude), Yahoos konsensus, rapportutfall
# för rapporter sedan förra morgonen (/rapportutfall med Sonnet) och bygget av sidan.
#
# Körs av den schemalagda uppgiften VeckansFinansMorgonrapport vardagar 08:10, samt fem
# minuter efter inloggning och upplåsning för att ta igen en missad morgon.
# Stegen körs bara om deras fil saknas, så skriptet kan köras om och tar då bara det som fattas:
#   1. data/morning/<datum>.json        morning.py (ingen handelsdag: avslutar utan fil)
#   2. data/consensus/<datum>.json      consensus.py --backup (märker bolag som redan rapporterat)
#   3. data/results/morning/<datum>.json run_results.ps1 <datum>; fallerar Claude byggs sidan ändå
#   4. npm run build                    om något steg kördes
# - Högst två försök per steg och dag (räknas i loggen), så att ett fel inte ger nya hämtningar
#   eller Claude-körningar vid varje upplåsning.
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
$Consensus = Join-Path $Root "data\consensus\$Today.json"
$Results = Join-Path $Root "data\results\morning\$Today.json"
$RunLog = Join-Path $LogDir "$Today.log"
$MaxAttempts = 2

function Attempts([string]$Marker) {
    if (Test-Path $RunLog) { @(Select-String -Path $RunLog -SimpleMatch $Marker).Count } else { 0 }
}
function Log([string]$Text) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text
    Add-Content -Path $RunLog -Value $line -Encoding UTF8
    Write-Output $line
}

$needReport = -not (Test-Path $Report) -and (Attempts "Startar morning.py") -lt $MaxAttempts
$needResults = -not (Test-Path $Results) -and (Attempts "Startar rapportutfall") -lt $MaxAttempts
if (-not $needReport -and (Test-Path $Report) -and (Test-Path $Consensus) -and -not $needResults) {
    Write-Output "Dagens morgonkörning är klar (eller har gjort sina försök) - inget att göra."
    exit 0
}
if (-not (Test-Path $Report) -and -not $needReport) {
    Write-Output "Redan $MaxAttempts försök med morgonrapporten i dag - avbryter. Se $RunLog."
    exit 0
}
$ran = $false

# 1. Morgonrapporten. Via cmd så att stderr (t.ex. yfinance-varningar) inte blir PowerShell-fel.
if ($needReport) {
    Log "Startar morning.py"
    & cmd.exe /c ".venv\Scripts\python.exe scripts\morning.py 2>&1" | ForEach-Object { Log "  $_" }
    Log "morning.py: exit $LASTEXITCODE"
    $ran = $true
}
if (-not (Test-Path $Report)) {
    Log "Ingen morgonrapport i dag (ingen handelsdag eller fel) - resten hoppas över."
    exit 0
}

# 2. Yahoos konsensus, en bild per handelsdag; bolag som redan rapporterat märks och används inte.
if (-not (Test-Path $Consensus)) {
    & cmd.exe /c ".venv\Scripts\python.exe scripts\consensus.py --backup 2>&1" |
        Where-Object { $_ -match '^(Konsensus|Säkerhetskopia|Ingen|Konsensusfilen)' } | ForEach-Object { Log "  $_" }
    Log "consensus.py: exit $LASTEXITCODE"
    $ran = $true
}

# 3. Rapportutfall sedan förra morgonen. Fel här får aldrig stoppa bygget.
if ($needResults) {
    Log "Startar rapportutfall"
    try {
        & powershell.exe -NoProfile -File (Join-Path $PSScriptRoot "run_results.ps1") -Week $Today |
            ForEach-Object { Log "  $_" }
    } catch {
        Log "  rapportutfall fallerade: $_"
    }
    $ran = $true
}

# 4. Bygget.
if ($ran) {
    $BuildLog = Join-Path $LogDir "$Today-build.log"
    & cmd.exe /c "npm run build > `"$BuildLog`" 2>&1"
    Log "npm run build: exit $LASTEXITCODE (logg: $BuildLog)"
}
Log "Klart"
