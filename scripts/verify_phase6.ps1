$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-True($condition, $message) {
    if (-not $condition) { throw $message }
}
function Get-FinalPath($response) {
    if ($response.BaseResponse.ResponseUri) { return $response.BaseResponse.ResponseUri.AbsolutePath }
    return $response.BaseResponse.RequestMessage.RequestUri.AbsolutePath
}
function Get-Snapshot {
    $out = docker compose exec -T web python manage.py shell -c "from inventory.models import Movement,PhotoDocument,Stock; print(f'{Movement.objects.count()}:{PhotoDocument.objects.count()}:{sum(Stock.objects.values_list('quantity',flat=True))}')" 2>&1 | Select-Object -Last 1
    Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar PostgreSQL.'
    return $out.ToString().Trim()
}

$base = 'http://127.0.0.1:8001'
$health = Invoke-RestMethod -Uri "$base/salud/"
Assert-True ($health.status -eq 'ok' -and $health.database -eq 'ok') 'La web o PostgreSQL no estan sanos.'
$before = Get-Snapshot
$cfg = @{}
Get-Content .env -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] }
}
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    Assert-True ([bool]$csrf) 'Falta CSRF de acceso.'
    $posted = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body @{
        username = $cfg["DEMO_${role}_EMAIL"]
        password = $cfg["DEMO_${role}_PASSWORD"]
        csrfmiddlewaretoken = $csrf
    } -WebSession $session -UseBasicParsing
    Assert-True ((Get-FinalPath $posted) -eq '/') "No inicio sesion $role."
    $chat = Invoke-WebRequest -Uri "$base/chat/" -WebSession $session -UseBasicParsing
    Assert-True ($chat.StatusCode -eq 200) "Chat no disponible para $role."
    $formCsrf = [regex]::Match($chat.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    Assert-True ([bool]$formCsrf) 'Falta CSRF del chat.'
    $answer = Invoke-WebRequest -Uri "$base/chat/" -Method Post -Body @{
        question = 'Stock de BARRA-100'
        csrfmiddlewaretoken = $formCsrf
    } -WebSession $session -UseBasicParsing
    Assert-True ($answer.StatusCode -eq 200 -and $answer.Content.Contains('BARRA-100') -and $answer.Content.Contains('Fuentes')) "Fallo la consulta de stock para $role."
    $blocked = Invoke-WebRequest -Uri "$base/chat/" -Method Post -Body @{
        question = 'Registra una venta de BARRA-100'
        csrfmiddlewaretoken = $formCsrf
    } -WebSession $session -UseBasicParsing
    Assert-True ($blocked.StatusCode -eq 200 -and $blocked.Content.Contains('solo consulta')) "No se rechazo una orden de escritura para $role."
    $api = Invoke-RestMethod -Uri "$base/api/v1/chat" -Method Post -Body '{"question":"Ultima temperatura"}' -ContentType 'application/json' -Headers @{'X-CSRFToken'=$formCsrf} -WebSession $session
    Assert-True ($api.intent -eq 'sensor' -and $api.as_of -and $api.sources.Count -ge 1) "La API del chat no devolvio fuente y fecha para $role."
    Assert-True ((Invoke-WebRequest -Uri "$base/inventario/" -WebSession $session -UseBasicParsing).StatusCode -eq 200) "Inventario no disponible para $role."
    Assert-True ((Invoke-WebRequest -Uri "$base/monitoreo/" -WebSession $session -UseBasicParsing).StatusCode -eq 200) "Monitoreo no disponible para $role."
}
$after = Get-Snapshot
Assert-True ($before -eq $after) "El chat altero inventario o fotos: $before -> $after"
$services = @(docker compose ps --services --status running)
Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar Docker.'
foreach ($service in @('db', 'web', 'sensor-gateway', 'worker')) {
    Assert-True ($service -in $services) "Falta el contenedor $service."
}
Write-Output "Fase 6 HTTP OK: ambos perfiles, stock, rechazo de escritura, API sensor con fecha/fuente y base intacta ($before)."
