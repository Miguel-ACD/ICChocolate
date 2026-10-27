$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/verify_phase2.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Falló la verificación de fases anteriores.' }

function Get-Status($url, $session, $method = 'Get', $body = $null, $headers = @{}) {
    try {
        return [int](Invoke-WebRequest -Uri $url -Method $method -Body $body -Headers $headers -WebSession $session -UseBasicParsing).StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}
function Assert-Status($url, $session, $expected) {
    $actual = Get-Status $url $session
    if ($actual -ne $expected) { throw "Respuesta $actual en $url; se esperaba $expected" }
}
$cfg = @{}
Get-Content .env | ForEach-Object { if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] } }
$base = 'http://127.0.0.1:8001'
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    if (-not $csrf) { throw 'Falta CSRF de acceso.' }
    $body = @{ username = $cfg["DEMO_${role}_EMAIL"]; password = $cfg["DEMO_${role}_PASSWORD"]; csrfmiddlewaretoken = $csrf }
    $post = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body $body -WebSession $session -UseBasicParsing
    if ($post.BaseResponse.RequestMessage.RequestUri.AbsolutePath -ne '/') { throw "Acceso $role falló." }
    Assert-Status "$base/monitoreo/" $session 200
    Assert-Status "$base/api/sensor/ultima/" $session 200
    Assert-Status "$base/api/sensor/historial/" $session 200
    $expected = if ($role -eq 'OWNER') { 200 } else { 403 }
    Assert-Status "$base/dispositivos/" $session $expected
    $data = Invoke-RestMethod -Uri "$base/api/sensor/ultima/" -WebSession $session
    if ($data.device -ne 'ESP32-01' -or -not $data.current_location -or -not $data.reading) {
        throw 'La API de sensor no conserva identidad, zona y última lectura.'
    }
}

docker compose up -d sensor-gateway | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'No se pudo iniciar el gateway del sensor.' }
$gateway = 'http://127.0.0.1:8002'
$gatewaySession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
$payload = '{"version":1,"ciclo_id":"00000000-0000-4000-8000-000000000001","estado":"INVALIDO","muestras_validas":0,"temperatura_c":null,"humedad_pct":null,"error_codigo":"SENSOR_LECTURA"}'
$unauthorized = Get-Status "$gateway/api/v1/dispositivos/me/ciclos" $gatewaySession 'Post' $payload @{Authorization='Bearer invalid-integration-test-token'; 'Content-Type'='application/json'}
if ($unauthorized -ne 401) { throw "Gateway aceptó token incorrecto: $unauthorized" }
if ((Get-Status "$gateway/inventario/" $gatewaySession) -ne 404) { throw 'El gateway expone una página interna.' }

$summary = docker compose exec -T web python manage.py shell -c "from inventory.models import SensorDevice,SensorAssignment,SensorReading; print(f'{SensorDevice.objects.count()}:{SensorAssignment.objects.filter(ended_at__isnull=True).count()}:{SensorReading.objects.filter(device__isnull=True).count()}')" 2>&1 | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar PostgreSQL.' }
$parts = $summary.ToString().Trim().Split(':')
if ([int]$parts[0] -lt 1 -or [int]$parts[1] -lt 1 -or [int]$parts[2] -ne 0) { throw "Estado de dispositivos incorrecto: $summary" }
Write-Output "Fase 3 local OK: pruebas previas, suite automatizada completa, roles HTTP, gateway, dispositivo y zona."
