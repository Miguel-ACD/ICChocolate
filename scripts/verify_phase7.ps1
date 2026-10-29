$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-True($condition, $message) {
    if (-not $condition) { throw $message }
}

function Get-Snapshot {
    $output = docker compose exec -T web python manage.py shell -c "from inventory.models import Movement,PhotoDocument,SensorReading,Stock; print(f'{Movement.objects.count()}:{PhotoDocument.objects.count()}:{PhotoDocument.objects.filter(movement__isnull=False).count()}:{SensorReading.objects.count()}:{sum(Stock.objects.values_list('quantity',flat=True))}')" 2>&1
    Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar PostgreSQL.'
    return ($output | Select-Object -Last 1).ToString().Trim().Split(':')
}

$before = Get-Snapshot
Assert-True ([int]$before[2] -ge 1) 'Falta confirmar una foto real desde el celular.'

& "$PSScriptRoot/verify_phase4.ps1"
Assert-True ($LASTEXITCODE -eq 0) 'Falló la suite integrada de fases 1 a 4.'
& "$PSScriptRoot/verify_phase5.ps1"
Assert-True ($LASTEXITCODE -eq 0) 'Falló la prueba HTTP de fotos.'
& "$PSScriptRoot/verify_phase6.ps1"
Assert-True ($LASTEXITCODE -eq 0) 'Falló la prueba HTTP del asistente.'

$after = Get-Snapshot
foreach ($index in @(0, 1, 2, 4)) {
    Assert-True ($before[$index] -eq $after[$index]) "Movimientos, fotos o stock cambiaron tras el reinicio: $($before -join ':') -> $($after -join ':')"
}
Assert-True ([int]$after[3] -ge [int]$before[3]) 'Se perdieron ciclos del ESP32 tras el reinicio.'

$bind = ''
Get-Content .env -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^ICCHOCOLATE_WEB_BIND=(.+)$') { $bind = $matches[1].Trim() }
}
Assert-True ($bind -and $bind -ne '127.0.0.1') 'Configura ICCHOCOLATE_WEB_BIND con la IPv4 local de Windows.'
$base = "http://${bind}:8003"
$health = Invoke-RestMethod -Uri "$base/salud/"
Assert-True ($health.status -eq 'ok' -and $health.database -eq 'ok') 'La dirección del celular o PostgreSQL no responde.'
$login = Invoke-WebRequest -Uri "$base/accounts/login/" -UseBasicParsing
Assert-True ($login.StatusCode -eq 200) 'No abre la página de acceso desde la IP local.'

Write-Output "Fase 7 local OK: suite completa, flujos HTTP anteriores, reinicio y persistencia; movimientos=$($after[0]), fotos=$($after[1]), fotos confirmadas=$($after[2]), ciclos=$($after[3]), unidades=$($after[4]); acceso LAN=$base."
