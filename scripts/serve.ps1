# Startar den lokala sidan (astro preview) på http://localhost:4321/veckans-finans/.
#
# Körs dolt av den schemalagda uppgiften VeckansFinansServer vid inloggning. Bygger först
# om dist/ saknas. Servern lyssnar bara på localhost. Utskrifter hamnar i logs/server.log.
# - Inmatningen kopplas till NUL: astro preview läser annars tangentbordet, och när datorn
#   somnar bryts den läsningen och Node kraschar med "read EPIPE".
# - Kraschar Node (felkod skild från 0) startar skriptet om servern efter en minut, högst
#   MaxRestarts gånger i följd; en körning som hållit i en timme nollställer räkningen.
#   Omstarten sker här och inte i Schemaläggaren, eftersom conhost --headless alltid
#   returnerar 0 till Schemaläggaren. Skriptet avslutar med Nodes felkod när försöken är slut.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null
$ServerLog = Join-Path $Root "logs\server.log"
$MaxRestarts = 3
$StableRun = New-TimeSpan -Hours 1

function Log([string]$Text) {
    Add-Content -Path $ServerLog -Encoding UTF8 -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text)
}

Log "serve.ps1 startar"
if (-not (Test-Path (Join-Path $Root "dist\index.html"))) {
    & cmd.exe /c "npm run build >> `"$ServerLog`" 2>&1"
}
$restarts = 0
while ($true) {
    $started = Get-Date
    & cmd.exe /c "npx astro preview --port 4321 --host localhost < NUL >> `"$ServerLog`" 2>&1"
    $code = $LASTEXITCODE
    if ($code -eq 0) { Log "astro preview avslutades (felkod 0)"; exit 0 }
    if ((Get-Date) - $started -ge $StableRun) { $restarts = 0 }
    if ($restarts -ge $MaxRestarts) {
        Log "astro preview kraschade (felkod $code) - $MaxRestarts omstarter i följd, ger upp"
        exit $code
    }
    $restarts++
    Log "astro preview kraschade (felkod $code) - startar om om en minut (omstart $restarts av $MaxRestarts)"
    Start-Sleep -Seconds 60
}
