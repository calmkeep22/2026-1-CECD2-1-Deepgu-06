# Backend-media integration tests

Place cross-service scenarios in this directory. The recommended Windows workflow
starts the isolated stack, publishes a local MP4 through FFmpeg, runs the test,
prints timing measurements, and removes the stack automatically.

```powershell
.\scripts\run-stream-integration.ps1 -VideoPath "C:\videos\sample.mp4"
```

The stack exposes backend `18000`, media API `19000`, MySQL `3307`, MediaMTX
RTMP `11935`, HLS `18888`, and MediaMTX API `19997` on localhost. It does not
require AWS credentials.

The test measures start API latency, Media API RUNNING transition, backend
callback/DB convergence, HLS playlist readiness, and stop API latency. Defaults
can be overridden with `TEST_START_API_MAX_SECONDS`, `TEST_RUNNING_MAX_SECONDS`,
`TEST_HLS_MAX_SECONDS`, and `TEST_STOP_API_MAX_SECONDS`.

For manual execution:

```powershell
$env:TEST_VIDEO_PATH = (Resolve-Path "C:\videos\sample.mp4").Path
$env:TEST_STREAM_KEY = "integration-stream"
docker compose -f compose.test.yml up --build -d mysql-test mediamtx-test media-test backend-test
$env:RUN_INTEGRATION_TESTS = "1"
.\BE\venv\Scripts\python.exe -m pytest tests\integration\test_stream_flow.py -v -s
docker compose -f compose.test.yml down -v
```
