# Startar den lokala sidan (astro preview) på http://localhost:4321/veckans-finans/.
#
# Körs dolt av den schemalagda uppgiften VeckansFinansServer vid inloggning. Bygger först
# om dist/ saknas. Servern lyssnar bara på localhost. Utskrifter hamnar i logs/server.log.
# Processen ligger kvar så länge servern körs; uppgiften startar om den vid krasch.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null
$ServerLog = Join-Path $Root "logs\server.log"

Add-Content -Path $ServerLog -Encoding UTF8 -Value ("{0:yyyy-MM-dd HH:mm:ss} serve.ps1 startar" -f (Get-Date))
if (-not (Test-Path (Join-Path $Root "dist\index.html"))) {
    & cmd.exe /c "npm run build >> `"$ServerLog`" 2>&1"
}
& cmd.exe /c "npx astro preview --port 4321 --host localhost >> `"$ServerLog`" 2>&1"
exit $LASTEXITCODE
