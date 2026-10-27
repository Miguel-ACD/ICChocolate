$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
& "$PSScriptRoot/verify_phase1.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Falló la verificación de fase 1.' }

function Assert-Status($url, $session, $expected) {
    try { $actual = [int](Invoke-WebRequest -Uri $url -WebSession $session -UseBasicParsing).StatusCode }
    catch {
        if (-not $_.Exception.Response) { throw }
        $actual = [int]$_.Exception.Response.StatusCode
    }
    if ($actual -ne $expected) { throw "Respuesta inesperada en $url : $actual (esperado $expected)" }
}

$cfg = @{}
Get-Content .env | ForEach-Object { if ($_ -match '^([A-Z_]+)=(.*)$') { $cfg[$matches[1]] = $matches[2] } }
$base = 'http://127.0.0.1:8001'
foreach ($role in @('OWNER', 'EMPLOYEE')) {
    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $login = Invoke-WebRequest -Uri "$base/accounts/login/" -WebSession $session -UseBasicParsing
    $csrf = [regex]::Match($login.Content, 'name="csrfmiddlewaretoken" value="([^"]+)"').Groups[1].Value
    if (-not $csrf) { throw 'Formulario de acceso sin CSRF.' }
    $body = @{ username = $cfg["DEMO_${role}_EMAIL"]; password = $cfg["DEMO_${role}_PASSWORD"]; csrfmiddlewaretoken = $csrf }
    $post = Invoke-WebRequest -Uri "$base/accounts/login/" -Method Post -Body $body -WebSession $session -UseBasicParsing
    if ($post.BaseResponse.RequestMessage.RequestUri.AbsolutePath -ne '/') { throw "Acceso fallido para $role." }
    $admin = if ($role -eq 'OWNER') { 200 } else { 403 }
    foreach ($path in @('/catalogo/', '/catalogo/equivalencias/', '/usuarios/')) {
        Assert-Status "$base$path" $session $admin
    }
    foreach ($path in @('/movimientos/borradores/', '/movimientos/conversion/nueva/')) {
        Assert-Status "$base$path" $session 200
    }
}
$summary = docker compose exec -T web python manage.py shell -c "from inventory.models import Equivalence,Stock; print(f'{Equivalence.objects.filter(active=True).count()}:{sum(Stock.objects.values_list('quantity',flat=True))}')" 2>&1 | Select-Object -Last 1
if ($LASTEXITCODE -ne 0) { throw 'No se pudo consultar PostgreSQL.' }
$parts = $summary.ToString().Trim().Split(':')
if ([int]$parts[0] -lt 2) { throw 'Faltan las equivalencias iniciales.' }
Write-Output "Fase 2 OK: suite completa y rutas HTTP por rol; equivalencias activas=$($parts[0]), stock=$($parts[1])."
