$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/verify_phase3.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Falló la verificación de fases anteriores.' }

function Status($url, $session) {
    try { return [int](Invoke-WebRequest -Uri $url -WebSession $session -UseBasicParsing).StatusCode }
    catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}
$cfg = @{}
Get-Content .env -Encoding UTF8 | ForEach-Object { if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] } }
$base = 'http://127.0.0.1:8001'
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    if (-not $csrf) { throw 'Falta CSRF del acceso.' }
    $body = @{ username = $cfg["DEMO_${role}_EMAIL"]; password = $cfg["DEMO_${role}_PASSWORD"]; csrfmiddlewaretoken = $csrf }
    $post = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body $body -WebSession $session -UseBasicParsing
    $finalPath = if ($post.BaseResponse.ResponseUri) { $post.BaseResponse.ResponseUri.AbsolutePath } else { $post.BaseResponse.RequestMessage.RequestUri.AbsolutePath }
    if ($finalPath -ne '/') { throw "Acceso fallido para $role (ruta final: $finalPath)." }
    if ((Status "$base/alertas/" $session) -ne 200) { throw "Alertas no disponibles para $role." }
    $expected = if ($role -eq 'OWNER') { 200 } else { 403 }
    foreach ($path in @('/alertas/reglas/', '/alertas/destinatarios/')) {
        if ((Status "$base$path" $session) -ne $expected) { throw "Permisos incorrectos en $path para $role." }
    }
}
$services = @(docker compose ps --services --status running)
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar Docker.' }
foreach ($name in @('db','web','sensor-gateway','worker')) {
    if ($name -notin $services) { throw "No está activo el servicio $name." }
}
$summary = docker compose exec -T web python manage.py shell -c "from inventory.models import AlertRule,AlertEpisode,AlertNotification,SensorReading; print(f'{AlertRule.objects.filter(ended_at__isnull=True).count()}:{AlertEpisode.objects.filter(status='ACTIVO').count()}:{AlertNotification.objects.filter(channel='WEB').count()}:{SensorReading.objects.count()}')" 2>&1 | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar PostgreSQL.' }
$values = $summary.ToString().Trim().Split(':')
if ([int]$values[0] -lt 1 -or [int]$values[1] -gt [int]$values[0] -or [int]$values[2] -lt 1) {
    throw "Faltan reglas o alertas web de una lectura física: $summary"
}
$accepted = docker compose exec -T web python manage.py shell -c "from inventory.models import AlertNotification; print(AlertNotification.objects.filter(channel='EMAIL',status='ACEPTADA',episode__start_reading__device__code='ESP32-01',episode__start_reading__sample_count=4).count())" 2>&1 | Select-Object -Last 1
if ($LASTEXITCODE -ne 0 -or [int]$accepted -lt 1) { throw 'Falta un correo real aceptado y vinculado al ESP32.' }
Write-Output "Fase 4 local OK: suite completa, permisos HTTP, trabajador, avisos web y correo SMTP real; reglas=$($values[0]), avisos=$($values[2]), ciclos=$($values[3]), correos aceptados=$accepted."
