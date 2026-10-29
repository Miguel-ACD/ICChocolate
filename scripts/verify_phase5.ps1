$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-True($condition, $message) {
    if (-not $condition) { throw $message }
}
function Get-FinalPath($response) {
    if ($response.BaseResponse.ResponseUri) { return $response.BaseResponse.ResponseUri.AbsolutePath }
    return $response.BaseResponse.RequestMessage.RequestUri.AbsolutePath
}
function Get-Status($url, $session) {
    try { return [int](Invoke-WebRequest -Uri $url -WebSession $session -UseBasicParsing).StatusCode }
    catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}

$base = 'http://127.0.0.1:8001'
$health = Invoke-RestMethod -Uri "$base/salud/"
Assert-True ($health.status -eq 'ok' -and $health.database -eq 'ok') 'La web o PostgreSQL no están sanos.'
$cfg = @{}
Get-Content .env -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] }
}
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    Assert-True ([bool]$csrf) 'Falta CSRF del acceso.'
    $post = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body @{
        username = $cfg["DEMO_${role}_EMAIL"]
        password = $cfg["DEMO_${role}_PASSWORD"]
        csrfmiddlewaretoken = $csrf
    } -WebSession $session -UseBasicParsing
    Assert-True ((Get-FinalPath $post) -eq '/') "Falló el acceso de $role."
    $page = Invoke-WebRequest -Uri "$base/documentos/nuevo/" -WebSession $session -UseBasicParsing
    Assert-True ($page.StatusCode -eq 200 -and $page.Content.Contains('accept="image/jpeg,image/png"') -and -not $page.Content.Contains('capture="environment"')) "El selector de fotos o archivos no está disponible para $role."
    Assert-True ((Get-Status "$base/inventario/" $session) -eq 200) "Inventario no está disponible para $role."
    Assert-True ((Get-Status "$base/documentos/00000000-0000-4000-8000-000000000001/revisar/" $session) -eq 404) 'Una revisión inexistente no devolvió 404.'
    $uploadCsrf = [regex]::Match($page.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    Assert-True ([bool]$uploadCsrf) 'Falta CSRF del formulario de fotos.'
    try {
        $bad = Invoke-WebRequest -Uri "$base/documentos/" -Method Post -Body @{
            kind = 'BOLETA'; csrfmiddlewaretoken = $uploadCsrf
        } -WebSession $session -UseBasicParsing
        $badStatus = [int]$bad.StatusCode
    } catch {
        if (-not $_.Exception.Response) { throw }
        $badStatus = [int]$_.Exception.Response.StatusCode
    }
    Assert-True ($badStatus -eq 400) "La carga sin imagen no fue rechazada para $role."
}

$summary = docker compose exec -T web python manage.py shell -c "from inventory.models import Movement,PhotoDocument,Stock; print(f'{Movement.objects.count()}:{PhotoDocument.objects.count()}:{sum(Stock.objects.values_list('quantity',flat=True))}')" 2>&1 | Select-Object -Last 1
Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar PostgreSQL.'
$services = @(docker compose ps --services --status running)
Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar Docker.'
foreach ($name in @('db', 'web', 'sensor-gateway', 'worker')) {
    Assert-True ($name -in $services) "Falta el contenedor $name."
}
Write-Output "Fase 5 HTTP OK: cámara para ambos perfiles, CSRF, carga inválida rechazada, 404 privado, inventario y salud; movimientos:fotos:unidades=$summary."
