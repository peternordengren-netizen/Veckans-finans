# Öppnar Veckans finans i webbläsaren och startar servern först om den inte svarar.
#
# Används av skrivbordsgenvägen "Veckans finans". Startar den schemalagda uppgiften
# VeckansFinansServer om sidan inte svarar och väntar högst 30 sekunder på den.

$Url = "http://localhost:4321/veckans-finans/"

function Test-Site {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-Site)) {
    Start-ScheduledTask -TaskName "VeckansFinansServer"
    $deadline = (Get-Date).AddSeconds(30)
    while (-not (Test-Site) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }
}
Start-Process $Url
