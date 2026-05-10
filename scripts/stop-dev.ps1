param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$managePy = Join-Path $projectRoot "manage.py"
$escapedPath = [Regex]::Escape($managePy)
$killed = @()

$processes = Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq "python.exe" -and
        $_.CommandLine -match $escapedPath -and
        $_.CommandLine -match "runserver"
    }

foreach ($proc in $processes) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        $killed += $proc.ProcessId
    } catch {
        Write-Warning ("Nao foi possivel encerrar o PID {0}: {1}" -f $proc.ProcessId, $_.Exception.Message)
    }
}

$listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
foreach ($listener in $listeners) {
    if ($listener.OwningProcess -and $listener.OwningProcess -notin $killed) {
        try {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
            $killed += $listener.OwningProcess
        } catch {
            Write-Warning ("Nao foi possivel liberar a porta {0} do PID {1}: {2}" -f $Port, $listener.OwningProcess, $_.Exception.Message)
        }
    }
}

if ($killed.Count -eq 0) {
    Write-Host "Nenhum runserver antigo encontrado."
} else {
    $unique = $killed | Sort-Object -Unique
    Write-Host ("Runservers antigos encerrados: {0}" -f ($unique -join ", "))
}
