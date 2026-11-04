# Local load smoke test

This is a short local comparison test, not a production capacity guarantee.

It measures:

- authenticated backend polling latency and failure rate;
- concurrent RTMP publishers;
- HLS manifest request latency and failure rate;
- WebRTC player/WHEP page availability (not real peer concurrency);
- backend, media API, and MediaMTX Docker resource snapshots.

Install the load-test dependency:

```powershell
BE\venv\Scripts\python.exe -m pip install -r tests\performance\requirements-test.txt
```

Run a 30-second smoke test:

```powershell
.\scripts\run-load-smoke.ps1 -VideoPath "C:\videos\sample.mp4"
```

Increase the short test load without turning it into a stability test:

```powershell
.\scripts\run-load-smoke.ps1 `
  -VideoPath "C:\videos\sample.mp4" `
  -StreamCount 5 `
  -ApiUsers 20 `
  -MediaUsers 10 `
  -RunSeconds 60
```

Real concurrent WebRTC peers require browser or WebRTC-native clients. Do not
interpret the WebRTC page probe as a peer-capacity measurement.

## Real WebRTC playback smoke test

This test launches separate headless Chrome or Edge contexts and verifies that
each MediaMTX `<video>` element reaches a playable state and that its
`currentTime` continues to increase. It also reports time to first playback and
samples MediaMTX Docker CPU and memory once per second, including average and
maximum values in the JSON report.

Install the test dependencies into the existing virtual environment:

```powershell
BE\venv\Scripts\python.exe -m pip install -r tests\performance\requirements-test.txt
```

Run the default 1, 3, and 5 concurrent-peer stages. Each stage is measured
three times after a warm-up, and the stage order rotates between repeats:

```powershell
.\scripts\run-webrtc-peer-smoke.ps1 -VideoPath "C:\videos\sample.mp4"
```

Use custom peer stages without turning the test into a long stability run:

```powershell
.\scripts\run-webrtc-peer-smoke.ps1 `
  -VideoPath "C:\videos\sample.mp4" `
  -PeerCounts 2,4,6 `
  -RepeatCount 3 `
  -PlaybackSeconds 3
```

The JSON report contains success rate, first-playback median and p95, and
MediaMTX CPU and memory averages and maxima for each peer-count stage.

This is still a short local playback smoke test. It does not model WAN latency,
packet loss, NAT traversal, TURN usage, or production capacity.
