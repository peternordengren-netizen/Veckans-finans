# Rapportutfall: /rapportutfall med Claude Code (Sonnet) i omgångar om 20, sedan scripts/results.py
# (sammanslagning, jämförelse med föregående år och förväntan) och säkerhetskopia.
#
# Tre lägen (se scripts/report_list.py):
#   -Week 2026-W43   måndagens uppsamling (anropas av run_weekly.ps1): det som morgnarna missat
#   -Week 2026-10-20 morgonkörningen (anropas av run_morning.ps1): rapporter sedan förra körningen;
#                    tidsfönstret skapas och sparas först
#   -Week 2026-10-20T1745 uppdateringen (anropas av run_update.ps1), som morgonkörningen.
# Claude körs bara om fönstret innehåller rapporter. Nås Claudes användningsgräns avbryts omgångarna,
# raden "Rapportutfall: räknas inte som försök …" loggas (anroparen räknar då inte försöket) och en
# engångsuppgift kör "run_results.ps1 -Week <läge> -Build" fem minuter efter återställningen.
# -Build: bygg om sidan efteråt (används av det nya försöket).
# - En omgång vars fil redan finns och klarar valideringen körs inte om (går att återuppta).
# - Claude körs i läget dontAsk med samma sorts begränsade lista som veckokörningen: läsa,
#   skriva bara i data/results/, och bara report_list.py och validate.py.
# - Loggar i logs/weekly/ (vecka) eller logs/morning/ (dag): <läge>-rapportutfall.log och
#   -rapportutfall-<N>.json/.err.
# Exit-kod 0 även om Claude-steget fallerar; anroparen bygger sidan ändå.

param(
    [Parameter(Mandatory = $true)][string]$Week,
    [switch]$Build
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "claude_limit.ps1")
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$IsUpdate = $Week -match '^\d{4}-\d{2}-\d{2}T\d{4}$'
$IsDay = $IsUpdate -or $Week -match '^\d{4}-\d{2}-\d{2}$'  # körning med eget tidsfönster
if (-not $IsDay -and $Week -notmatch '^\d{4}-W\d{2}$') { throw "Ogiltig vecka, dag eller uppdatering: '$Week'" }
$LogDir = Join-Path $Root $(if ($IsUpdate) { "logs\updates" } elseif ($IsDay) { "logs\morning" } else { "logs\weekly" })
New-Item -ItemType Directory -Force $LogDir | Out-Null
$BatchDir = if ($IsUpdate) { "data\results\updates\$Week" } elseif ($IsDay) { "data\results\morning\$Week" } else { "data\results\$Week" }

$RunLog = Join-Path $LogDir "$Week-rapportutfall.log"
function Log([string]$Text) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text
    Add-Content -Path $RunLog -Value $line -Encoding UTF8
    Write-Output $line
}

$Claude = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
if (-not (Test-Path $Claude)) { Log "Hittar inte Claude Code-CLI:n ($Claude) - avbryter."; exit 0 }
foreach ($name in @(Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object Name)) {
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}

# Ett lås för alla körningar (morgon, uppdatering, vecka): fönstren skapas efter varandra och
# Claude körs aldrig i två omgångar samtidigt. Väntar högst 25 minuter på en pågående körning.
$Lock = New-Object System.Threading.Mutex($false, "Local\VeckansFinansRapportutfall")
try {
    if (-not $Lock.WaitOne([TimeSpan]::FromMinutes(25))) { Log "En annan rapportutfallskörning pågår fortfarande - avbryter."; exit 0 }
} catch [System.Threading.AbandonedMutexException] { }  # förra ägaren avslutades utan att släppa låset

$listArgs = @("scripts\report_list.py", $Week, "--antal-omgangar")
if ($IsDay) { $listArgs += "--skapa-fonster" }
$Batches = [int](& .venv\Scripts\python.exe @listArgs)
Log "Rapportutfall ${Week}: $Batches omgångar"
if ($Batches -eq 0) { Log "Inga rapporter att ta fram."; exit 0 }

$Allowed = @(
    "Read", "Glob", "Grep",
    "Edit(./data/results/**)",
    "Bash(.venv/Scripts/python scripts/report_list.py:*)",
    "Bash(.venv/Scripts/python scripts/validate.py:*)"
)
$Disallowed = @("PowerShell", "WebFetch", "WebSearch")
function Quote([string]$s) { '"' + ($s -replace '"', '\"') + '"' }

function BatchApproved([string]$File) {
    if (-not (Test-Path $File)) { return $false }
    & cmd.exe /c ".venv\Scripts\python.exe scripts\validate.py $File > nul 2>&1"
    return $LASTEXITCODE -eq 0
}

# Varje omgång får högst MaxAttempts Claude-körningar i samma körning: underkänns den första görs
# ett nytt försök direkt (Claude ser valideringsfelen när den kör validate.py). Loggarna för
# försök 2 heter -rapportutfall-<N>-2.json/.err, så att första försökets logg finns kvar.
$MaxAttempts = 2
$stopForLimit = $false
for ($n = 1; $n -le $Batches -and -not $stopForLimit; $n++) {
    $BatchFile = "$BatchDir\omgang-$n.json"
    if (BatchApproved $BatchFile) { Log "omgång ${n}: finns redan och är godkänd - hoppar över"; continue }
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $ArgList = @("-p", (Quote "/rapportutfall $Week $n"), "--model", "sonnet", "--permission-mode", "dontAsk",
            "--allowedTools") + ($Allowed | ForEach-Object { Quote $_ }) +
            @("--disallowedTools") + ($Disallowed | ForEach-Object { Quote $_ }) +
            @("--strict-mcp-config", "--no-session-persistence", "--output-format", "json")
        $Suffix = if ($attempt -gt 1) { "-$attempt" } else { "" }
        $JsonOut = Join-Path $LogDir "$Week-rapportutfall-$n$Suffix.json"
        $ErrOut = Join-Path $LogDir "$Week-rapportutfall-$n$Suffix.err"
        Log "omgång ${n}: startar Claude Code (Sonnet), försök $attempt"
        try {
            $proc = Start-Process -FilePath $Claude -ArgumentList $ArgList -NoNewWindow -PassThru -Wait `
                -RedirectStandardOutput $JsonOut -RedirectStandardError $ErrOut
            $r = Get-Content $JsonOut -Raw -Encoding UTF8 | ConvertFrom-Json
            Log ("omgång ${n}: exit $($proc.ExitCode), turer $($r.num_turns), " +
                "$([math]::Round($r.duration_ms / 60000, 1)) min, nekade anrop $(@($r.permission_denials).Count)")
        } catch {
            Log "omgång ${n}: Claude-steget fallerade: $_"
        }
        $limit = Test-ClaudeLimit $JsonOut "rapportutfall $Week omgång $n"
        if ($limit.Limit) {
            # Inga fler omgångar nu; anroparen schemalägger ett nytt försök efter återställningen.
            $limit.Lines | ForEach-Object { Log "omgång ${n}: $_" }
            Log "Rapportutfall: $LimitMarkerSuffix"
            Log (Register-ClaudeRetry ("VeckansFinansOmforsok-" + ($Week -replace '[^0-9A-Za-z-]', '')) `
                "scripts\run_results.ps1" "-Week $Week -Build" $limit.ResetAt)
            $stopForLimit = $true
            break
        }
        if (BatchApproved $BatchFile) { Log "omgång ${n}: godkänd (försök $attempt)"; break }
        $first = (& cmd.exe /c ".venv\Scripts\python.exe scripts\validate.py $BatchFile 2>&1" | Select-String '^\s+fel:' | Select-Object -First 1)
        Log "omgång ${n}: underkänd efter försök $attempt$(if ($first) { ': ' + $first.Line.Trim() })"
    }
}

$mergeArgs = @("scripts\results.py", $Week)
if ($IsDay) { $mergeArgs += "--backup" }
& cmd.exe /c (".venv\Scripts\python.exe " + ($mergeArgs -join " ") + " 2>&1") | ForEach-Object { Log "  $_" }
$code = $LASTEXITCODE
Log "results.py: exit $code"
if ($code -eq 0 -and -not $IsDay) {
    & cmd.exe /c ".venv\Scripts\python.exe scripts\backup_week.py $Week 2>&1" | Select-Object -Last 1 | ForEach-Object { Log "  $_" }
}
if ($Build) {
    $BuildLog = Join-Path $LogDir "$Week-rapportutfall-build.log"
    & cmd.exe /c "npm run build > `"$BuildLog`" 2>&1"
    Log "npm run build: exit $LASTEXITCODE (logg: $BuildLog)"
}
Log "Klart"
exit 0
