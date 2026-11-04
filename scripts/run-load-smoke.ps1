param(
    [Parameter(Mandatory = $true)]
    [string]$VideoPath,

    [ValidateRange(1, 10)]
    [int]$StreamCount = 3,

    [ValidateRange(1, 100)]
    [int]$ApiUsers = 5,

    [ValidateRange(1, 100)]
    [int]$MediaUsers = 3,

    [ValidateRange(1, 100)]
    [int]$SpawnRate = 2,

    [ValidateRange(10, 300)]
    [int]$RunSeconds = 30,

    [switch]$KeepStack
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $repositoryRoot "compose.test.yml"
$pythonPath = Join-Path $repositoryRoot "BE\venv\Scripts\python.exe"
$locustFile = Join-Path $repositoryRoot "tests\locustfile.py"
$prepareScript = Join-Path $repositoryRoot "tests\performance\prepare_load_test.py"
$resolvedVideo = (Resolve-Path -LiteralPath $VideoPath).Path

if (-not (Test-Path -LiteralPath $resolvedVideo -PathType Leaf)) {
    throw "Video file does not exist: $resolvedVideo"
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Backend virtual environment is missing."
}

& $pythonPath -c "import locust" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Locust is missing. Install tests\performance\requirements-test.txt into BE\venv."
}

docker version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not available."
}

$env:TEST_VIDEO_PATH = $resolvedVideo.Replace("\", "/")
$env:LOAD_TEST_EMAIL = "loadtest@example.com"
$env:LOAD_TEST_PASSWORD = "loadtest-password"
$env:LOAD_BACKEND_URL = "http://127.0.0.1:18000"
$env:LOAD_HLS_URL = "http://127.0.0.1:18888"
$env:LOAD_WEBRTC_URL = "http://127.0.0.1:8889"
$env:LOAD_API_USERS = $ApiUsers.ToString()
$env:LOAD_MEDIA_USERS = $MediaUsers.ToString()
$env:LOAD_CAMERA_IDS = ((1..$StreamCount | ForEach-Object { "load-camera-$_" }) -join ",")
$env:LOAD_STREAM_KEYS = ((1..$StreamCount | ForEach-Object { "load-stream-$_" }) -join ",")

function Wait-HttpReady {
    param([string]$Url, [int]$TimeoutSeconds = 90)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -eq 200) { return }
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

    Wait-HttpReady "http://127.0.0.1:18000/ready"
    Wait-HttpReady "http://127.0.0.1:19000/health"

    & $pythonPath $prepareScript setup --stream-count $StreamCount
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare load test data." }

    for ($index = 1; $index -le $StreamCount; $index++) {
        $env:TEST_STREAM_KEY = "load-stream-$index"
        $containerName = "deepgu-load-publisher-$index"
        docker compose -f $composeFile --profile streaming run -d --no-deps --name $containerName stream-publisher | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to start $containerName" }
    }

    Start-Sleep -Seconds 8

    Write-Host "`n=== Docker resources before load ==="
    docker stats --no-stream --format "table {{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.NetIO}}" `
        deepgu-test-backend-test-1 deepgu-test-media-test-1 deepgu-test-mediamtx-test-1

    $totalUsers = $ApiUsers + $MediaUsers
    & $pythonPath -m locust `
        -f $locustFile `
        --headless `
        --users $totalUsers `
        --spawn-rate $SpawnRate `
        --run-time "${RunSeconds}s" `
        --only-summary `
        --exit-code-on-error 1 `
        FEPollingUser MediaPlaybackProbeUser
    $exitCode = $LASTEXITCODE

    Write-Host "`n=== Docker resources after load ==="
    docker stats --no-stream --format "table {{.Name}}`t{{.CPUPerc}}`t{{.MemUsage}}`t{{.NetIO}}" `
        deepgu-test-backend-test-1 deepgu-test-media-test-1 deepgu-test-mediamtx-test-1
}
finally {
    if (-not $KeepStack) {
        try { & $pythonPath $prepareScript cleanup } catch { }
        docker compose -f $composeFile --profile streaming down -v --remove-orphans
    }
    Pop-Location
}

exit $exitCode
