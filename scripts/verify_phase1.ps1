$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Assert-True($condition, $message) {
    if (-not $condition) { throw $message }
}

function Get-HttpStatus($url, $session) {
    try {
        return [int](Invoke-WebRequest -Uri $url -WebSession $session -UseBasicParsing).StatusCode
    } catch {
        if ($_.Exception.Response) { return [int]$_.Exception.Response.StatusCode }
        throw
    }
}

function Get-InventorySnapshot {
    $output = docker compose exec -T web python manage.py shell -c "from inventory.models import Stock,Movement,SensorReading; print(f'{Stock.objects.count()}:{Movement.objects.count()}:{SensorReading.objects.count()}:{sum(Stock.objects.values_list('quantity',flat=True))}')" 2>&1
    Assert-True ($LASTEXITCODE -eq 0) 'No se pudo consultar PostgreSQL.'
    return ($output | Select-Object -Last 1).ToString().Trim()
}

function Wait-ForHealth {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-RestMethod -Uri 'http://127.0.0.1:8001/salud/' -TimeoutSec 2
            if ($response.status -eq 'ok' -and $response.database -eq 'ok') { return }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw 'La web o PostgreSQL no respondió sano tras el reinicio.'
}

$cfg = @{}
Get-Content .env -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] }
}
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    Assert-True ($cfg["DEMO_${role}_EMAIL"] -and $cfg["DEMO_${role}_PASSWORD"]) "Falta una credencial local de $role."
}

docker compose up -d db web | Out-Null
Assert-True ($LASTEXITCODE -eq 0) 'No se pudo iniciar ICChocolate.'
Wait-ForHealth

docker compose run --rm web python manage.py makemigrations --check --dry-run
Assert-True ($LASTEXITCODE -eq 0) 'Los modelos no coinciden con las migraciones.'
docker compose exec -T web python manage.py migrate --check
Assert-True ($LASTEXITCODE -eq 0) 'Hay migraciones pendientes.'
docker compose run --rm web python manage.py test inventory -v 1
Assert-True ($LASTEXITCODE -eq 0) 'Fallaron las pruebas automatizadas.'

$base = 'http://127.0.0.1:8001'
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    Assert-True ([bool]$csrf) 'No se encontró el token CSRF del formulario.'
    $body = @{ username = $cfg["DEMO_${role}_EMAIL"]; password = $cfg["DEMO_${role}_PASSWORD"]; csrfmiddlewaretoken = $csrf }
    $post = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body $body -WebSession $session -UseBasicParsing
    $finalPath = if ($post.BaseResponse.ResponseUri) { $post.BaseResponse.ResponseUri.AbsolutePath } else { $post.BaseResponse.RequestMessage.RequestUri.AbsolutePath }
    Assert-True ($finalPath -eq '/') "Falló el acceso HTTP de $role (ruta final: $finalPath)."
    Assert-True ((Get-HttpStatus "$base/inventario/" $session) -eq 200) "$role no puede ver Inventario."
    $expectedAdmin = if ($role -eq 'OWNER') { 200 } else { 403 }
    Assert-True ((Get-HttpStatus "$base/catalogo/productos/nuevo/" $session) -eq $expectedAdmin) "Permiso administrativo incorrecto para $role."
}

$before = Get-InventorySnapshot
docker compose restart db web | Out-Null
Assert-True ($LASTEXITCODE -eq 0) 'No se pudo reiniciar ICChocolate.'
Wait-ForHealth
$after = Get-InventorySnapshot
$beforeParts = $before.Split(':')
$afterParts = $after.Split(':')
Assert-True ($beforeParts.Count -eq 4 -and $afterParts.Count -eq 4) 'Snapshot de PostgreSQL incorrecto.'
foreach ($index in @(0, 1, 3)) {
    Assert-True ($beforeParts[$index] -eq $afterParts[$index]) "Inventario cambió tras el reinicio: $before -> $after"
}
Assert-True ([int]$afterParts[2] -ge [int]$beforeParts[2]) "Se perdieron ciclos del sensor: $before -> $after"
Write-Output "Fase 1 OK: pruebas, sesiones, permisos y persistencia ($before -> $after)."
