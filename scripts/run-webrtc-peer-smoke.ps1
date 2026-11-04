param(
    [Parameter(Mandatory = $true)]
    [string]$VideoPath,

    [ValidateRange(1, 10)]
    [int]$StreamCount = 3,

    [ValidateRange(1, 20)]
    [int[]]$PeerCounts = @(1, 3, 5),

    [ValidateRange(1, 30)]
    [int]$PlaybackSeconds = 2,

    [ValidateRange(1, 10)]
    [int]$RepeatCount = 3,

    [switch]$KeepStack
)

$ErrorActionPreference = "Stop"

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFile = Join-Path $repositoryRoot "compose.test.yml"
$pythonPath = Join-Path $repositoryRoot "BE\venv\Scripts\python.exe"
$testScript = Join-Path $repositoryRoot "tests\performance\test_webrtc_playback.py"
$resolvedVideo = (Resolve-Path -LiteralPath $VideoPath).Path
$resultDirectory = Join-Path $repositoryRoot ".tmp-webrtc-smoke"
$resultPath = Join-Path $resultDirectory "webrtc-peer-results.json"

if (-not (Test-Path -LiteralPath $resolvedVideo -PathType Leaf)) {
    throw "Video file does not exist: $resolvedVideo"
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "Backend virtual environment is missing."
}

& $pythonPath -c "import playwright" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Playwright is missing. Install tests\performance\requirements-test.txt into BE\venv."
}

docker version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is not available."
}

$env:TEST_VIDEO_PATH = $resolvedVideo.Replace("\", "/")
$streamKeys = 1..$StreamCount | ForEach-Object { "webrtc-stream-$_" }
$exitCode = 1

try {
    Push-Location $repositoryRoot

    docker compose -f $composeFile --profile streaming down -v --remove-orphans
    docker compose -f $composeFile --profile streaming build stream-publisher
    docker compose -f $composeFile up -d mediamtx-test

    foreach ($index in 1..$StreamCount) {
        $env:TEST_STREAM_KEY = "webrtc-stream-$index"
        $containerName = "deepgu-webrtc-publisher-$index"
        docker compose -f $composeFile --profile streaming run -d --no-deps --name $containerName stream-publisher | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to start $containerName" }
    }

    $deadline = (Get-Date).AddSeconds(45)
    foreach ($streamKey in $streamKeys) {
        $url = "http://127.0.0.1:8889/live/$streamKey/"
        $ready = $false
        while ((Get-Date) -lt $deadline) {
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
                if ($response.StatusCode -eq 200) {
                    $ready = $true
                    break
                }
            }
            catch {
                Start-Sleep -Seconds 1
            }
        }
        if (-not $ready) { throw "Timed out waiting for $url" }
    }

    New-Item -ItemType Directory -Path $resultDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $resultPath) {
        Remove-Item -LiteralPath $resultPath -Force
    }
    & $pythonPath $testScript `
        --stream-keys $streamKeys `
        --peer-counts $PeerCounts `
        --repeat-count $RepeatCount `
        --playback-seconds $PlaybackSeconds `
        --docker-containers deepgu-test-mediamtx-test-1 `
        --json-out $resultPath
    $exitCode = $LASTEXITCODE

    if (Test-Path -LiteralPath $resultPath) {
        Write-Host "`nDetailed result: $resultPath"
    }
}
finally {
    if (-not $KeepStack) {
        docker compose -f $composeFile --profile streaming down -v --remove-orphans
    }
    Pop-Location
}

exit $exitCode
