from app.services import hls_service


def test_start_hls_stream_registers_starting_stream(monkeypatch):
    camera_id = "camera-test-01"
    stream_key = "stream-test-01"

    monkeypatch.setattr(hls_service, "_check_active", lambda _: False)

    result = hls_service.start_hls_stream(
        camera_id=camera_id,
        input_url=f"rtmp://localhost/live/{stream_key}",
    )
    status = hls_service.get_stream_status(camera_id)

    assert result["camera_id"] == camera_id
    assert result["status"] == "STARTING"
    assert result["running"] is False
    assert result["hls_url"] == f"/live/{stream_key}/index.m3u8"

    assert status["camera_id"] == camera_id
    assert status["status"] == "STARTING"
    assert status["running"] is False


def test_start_hls_stream_returns_running_for_active_path(monkeypatch):
    monkeypatch.setattr(hls_service, "_check_active", lambda _: True)

    result = hls_service.start_hls_stream(
        camera_id="camera-02",
        input_url="rtmp://localhost/live/stream-02",
    )

    assert result["status"] == "RUNNING"
    assert result["running"] is True


def test_stop_hls_stream_removes_entry_and_sends_callback(monkeypatch):
    callbacks = []
    monkeypatch.setattr(hls_service, "_check_active", lambda _: False)
    monkeypatch.setattr(
        hls_service,
        "send_callback",
        lambda *args: callbacks.append(args),
    )
    hls_service.start_hls_stream(
        camera_id="camera-03",
        input_url="rtmp://localhost/live/stream-03",
        callback_url="http://backend/internal/streams/callback",
    )

    result = hls_service.stop_hls_stream("camera-03")
    status = hls_service.get_stream_status("camera-03")

    assert result["status"] == "STOPPED"
    assert status["status"] == "STOPPED"
    assert callbacks == [
        (
            "http://backend/internal/streams/callback",
            "camera-03",
            "STOPPED",
            "/live/stream-03/index.m3u8",
        )
    ]
