param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\\Scripts\\python.exe"
$managePy = Join-Path $projectRoot "manage.py"
$bindAddress = "{0}:{1}" -f $HostAddress, $Port
$currentPid = $PID

if (-not (Test-Path $pythonExe)) {
    throw "Virtualenv nao encontrada. Execute scripts\\bootstrap.ps1 primeiro."
}

function Stop-ProjectRunservers {
    param(
        [string]$ManagePyPath,
        [int]$SelfPid
    )

    $escapedPath = [Regex]::Escape($ManagePyPath)
    $processes = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -eq "python.exe" -and
            $_.ProcessId -ne $SelfPid -and
            $_.CommandLine -match $escapedPath -and
            $_.CommandLine -match "runserver"
        }

    foreach ($proc in $processes) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host ("Encerrado processo antigo do projeto: PID {0}" -f $proc.ProcessId)
        } catch {
            Write-Warning ("Nao foi possivel encerrar o PID {0}: {1}" -f $proc.ProcessId, $_.Exception.Message)
        }
    }
}

function Stop-PortOwner {
    param(
        [int]$LocalPort,
        [int]$SelfPid
    )

    $listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    foreach ($listener in $listeners) {
        if ($listener.OwningProcess -and $listener.OwningProcess -ne $SelfPid) {
            try {
                Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
                Write-Host ("Encerrado processo na porta {0}: PID {1}" -f $LocalPort, $listener.OwningProcess)
            } catch {
                Write-Warning ("Nao foi possivel liberar a porta {0} do PID {1}: {2}" -f $LocalPort, $listener.OwningProcess, $_.Exception.Message)
            }
        }
    }
}

Stop-ProjectRunservers -ManagePyPath $managePy -SelfPid $currentPid
Stop-PortOwner -LocalPort $Port -SelfPid $currentPid

$runserverArgs = @($managePy, "runserver", $bindAddress, "--noreload")
Write-Host "Subindo servidor sem autoreload para evitar multiplas instancias no Windows."

& $pythonExe @runserverArgs
