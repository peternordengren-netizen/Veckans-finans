# Rapportutfall för en vecka: /rapportutfall med Claude Code (Sonnet) i omgångar om 20, sedan
# scripts/results.py (sammanslagning, jämförelse med föregående år och förväntan) och säkerhetskopia.
#
# Anropas av scripts/run_weekly.ps1 efter veckosammanfattningen, men går att köra för sig:
#   powershell -NoProfile -File scripts\run_results.ps1 -Week 2026-W43
# - En omgång vars fil redan finns och klarar valideringen körs inte om (går att återuppta).
# - Claude körs i läget dontAsk med samma sorts begränsade lista som veckokörningen: läsa,
#   skriva bara i data/results/, och bara report_list.py och validate.py.
# - Loggar i logs/weekly/<vecka>-rapportutfall.log och -rapportutfall-<N>.json/.err.

param(
    [Parameter(Mandatory = $true)][string]$Week
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs\weekly"
New-Item -ItemType Directory -Force $LogDir | Out-Null
Set-Location $Root
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
if ($Week -notmatch '^\d{4}-W\d{2}$') { throw "Ogiltig vecka: '$Week'" }

$RunLog = Join-Path $LogDir "$Week-rapportutfall.log"
function Log([string]$Text) {
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Text
    Add-Content -Path $RunLog -Value $line -Encoding UTF8
    Write-Output $line
}

$Claude = Join-Path $env:USERPROFILE ".local\bin\claude.exe"
if (-not (Test-Path $Claude)) { Log "Hittar inte Claude Code-CLI:n ($Claude) - avbryter."; exit 1 }
foreach ($name in @(Get-ChildItem env: | Where-Object { $_.Name -match '^(CLAUDE|ANTHROPIC)' } | ForEach-Object Name)) {
    [Environment]::SetEnvironmentVariable($name, $null, "Process")
}

$Batches = [int](& .venv\Scripts\python.exe scripts\report_list.py $Week --antal-omgangar)
Log "Rapportutfall ${Week}: $Batches omgångar"

$Allowed = @(
    "Read", "Glob", "Grep",
    "Edit(./data/results/**)",
    "Bash(.venv/Scripts/python scripts/report_list.py:*)",
    "Bash(.venv/Scripts/python scripts/validate.py:*)"
)
$Disallowed = @("PowerShell", "WebFetch", "WebSearch")
function Quote([string]$s) { '"' + ($s -replace '"', '\"') + '"' }

for ($n = 1; $n -le $Batches; $n++) {
    $BatchFile = "data\results\$Week\omgang-$n.json"
    if (Test-Path $BatchFile) {
        & cmd.exe /c ".venv\Scripts\python.exe scripts\validate.py $BatchFile > nul 2>&1"
        if ($LASTEXITCODE -eq 0) { Log "omgång ${n}: finns redan och är godkänd - hoppar över"; continue }
    }
    $ArgList = @("-p", (Quote "/rapportutfall $Week $n"), "--model", "sonnet", "--permission-mode", "dontAsk",
        "--allowedTools") + ($Allowed | ForEach-Object { Quote $_ }) +
        @("--disallowedTools") + ($Disallowed | ForEach-Object { Quote $_ }) +
        @("--strict-mcp-config", "--no-session-persistence", "--output-format", "json")
    $JsonOut = Join-Path $LogDir "$Week-rapportutfall-$n.json"
    $ErrOut = Join-Path $LogDir "$Week-rapportutfall-$n.err"
    Log "omgång ${n}: startar Claude Code (Sonnet)"
    $proc = Start-Process -FilePath $Claude -ArgumentList $ArgList -NoNewWindow -PassThru -Wait `
        -RedirectStandardOutput $JsonOut -RedirectStandardError $ErrOut
    try {
        $r = Get-Content $JsonOut -Raw -Encoding UTF8 | ConvertFrom-Json
        $denied = @($r.permission_denials).Count
        Log ("omgång ${n}: exit $($proc.ExitCode), turer $($r.num_turns), " +
            "$([math]::Round($r.duration_ms / 60000, 1)) min, nekade anrop $denied")
    } catch {
        Log "omgång ${n}: exit $($proc.ExitCode), kunde inte läsa svaret ($JsonOut)"
    }
}

& cmd.exe /c ".venv\Scripts\python.exe scripts\results.py $Week 2>&1" | ForEach-Object { Log "  $_" }
$code = $LASTEXITCODE
Log "results.py: exit $code"
if ($code -eq 0) {
    & cmd.exe /c ".venv\Scripts\python.exe scripts\backup_week.py $Week 2>&1" | Select-Object -Last 1 | ForEach-Object { Log "  $_" }
}
Log "Klart"
