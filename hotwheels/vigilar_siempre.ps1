# Supervisor de Chicos Wheels + Bot Hot Wheels: lo mantiene vigilando siempre.
# Desde 2026-10-17 el monitor corre dentro de la app del 02 (app.py, puerto 3000).
# Cada 60 s revisa que algo escuche en el 3000 y el latido del monitor
# (hotwheels\latido.txt, se escribe en cada barrido completo). Si la app murio o
# el latido lleva mas de $MaxMin minutos sin actualizarse (monitor "ciego"),
# mata lo que quede y vuelve a arrancar app.py.
# Lo lanza la tarea programada "HotWheels_MonitorSiempre" al iniciar sesion.
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Split-Path -Parent $dir
$Puerto = 3000
$MaxMin = 10
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Get-AppPid {
    $c = Get-NetTCPConnection -State Listen -LocalPort $Puerto -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return $c.OwningProcess }
    return $null
}
function Latido-Fresco {
    $f = Join-Path $dir 'latido.txt'
    if (-not (Test-Path $f)) { return $false }
    return ((Get-Date) - (Get-Item $f).LastWriteTime).TotalMinutes -lt $MaxMin
}

$ultimoArranque = [datetime]::MinValue
while ($true) {
    try {
        $appPid = Get-AppPid
        $gracia = ((Get-Date) - $ultimoArranque).TotalMinutes -lt 3   # da tiempo a que escriba su primer latido
        if (-not $appPid -or (-not (Latido-Fresco) -and -not $gracia)) {
            if ($appPid) { & taskkill /PID $appPid /T /F | Out-Null }
            Start-Process -FilePath 'python' -ArgumentList "`"$app\app.py`"" -WorkingDirectory $app -WindowStyle Hidden
            $ultimoArranque = Get-Date
        }
    } catch {}
    Start-Sleep -Seconds 60
}
