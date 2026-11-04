param(
    [Parameter(Mandatory = $true)]
    [string]$VideoPath,

    [string]$StreamKey = "integration-stream",

    [switch]$KeepStack
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $repositoryRoot "compose.test.yml"
$pythonPath = Join-Path $repositoryRoot "BE\venv\Scripts\python.exe"
$testFile = Join-Path $repositoryRoot "tests\integration\test_stream_flow.py"
$resolvedVideo = (Resolve-Path -LiteralPath $VideoPath).Path

if (-not (Test-Path -LiteralPath $resolvedVideo -PathType Leaf)) {
    throw "Video file does not exist: $resolvedVideo"
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Backend virtual environment is missing. Create BE\venv and install BE\requirements-test.txt first."
}

docker version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not available. Start Docker Desktop and try again."
}

docker compose version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose is not available."
}

$env:TEST_VIDEO_PATH = $resolvedVideo.Replace("\", "/")
$env:TEST_STREAM_KEY = $StreamKey
$env:TEST_COMPOSE_FILE = $composeFile.Replace("\", "/")
$env:RUN_INTEGRATION_TESTS = "1"

function Wait-HttpReady {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 90
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "Timed out waiting for $Url"
}

$exitCode = 1

try {
    Push-Location $repositoryRoot

    docker compose -f $composeFile --profile streaming down -v --remove-orphans
    docker compose -f $composeFile up --build -d mysql-test mediamtx-test media-test backend-test

    Wait-HttpReady -Url "http://127.0.0.1:18000/ready"
    Wait-HttpReady -Url "http://127.0.0.1:19000/health"

    & $pythonPath -m pytest $testFile -v -s -p no:cacheprovider
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        docker compose -f $composeFile ps
        docker compose -f $composeFile logs --no-color --tail 200 backend-test media-test mediamtx-test stream-publisher
    }
}
finally {
    if (-not $KeepStack) {
        docker compose -f $composeFile --profile streaming down -v --remove-orphans
    }
    Pop-Location
}

exit $exitCode
