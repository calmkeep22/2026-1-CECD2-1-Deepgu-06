from app.api import stream as stream_api


def test_start_stream_builds_rtmp_url(client, monkeypatch):
    received = {}

    def fake_start(camera_id, input_url, callback_url):
        received.update(
            camera_id=camera_id,
            input_url=input_url,
            callback_url=callback_url,
        )
        return {
            "camera_id": camera_id,
            "status": "STARTING",
            "running": False,
            "hls_url": "/live/stream-01/index.m3u8",
        }

    monkeypatch.setattr(stream_api, "start_hls_stream", fake_start)

    response = client.post(
        "/streams/camera-01/start",
        json={
            "stream_key": "stream-01",
            "callback_url": "http://backend/internal/streams/callback",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "STARTING"
    assert received["camera_id"] == "camera-01"
    assert received["input_url"].endswith("/stream/stream-01")
    assert received["callback_url"] == "http://backend/internal/streams/callback"


def test_stop_stream_returns_service_result(client, monkeypatch):
    monkeypatch.setattr(
        stream_api,
        "stop_hls_stream",
        lambda camera_id: {
            "camera_id": camera_id,
            "status": "STOPPED",
            "running": False,
        },
    )

    response = client.post("/streams/camera-01/stop")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "STOPPED"


def test_start_stream_maps_value_error_to_bad_request(client, monkeypatch):
    def raise_invalid(*args, **kwargs):
        raise ValueError("invalid stream key")

    monkeypatch.setattr(stream_api, "start_hls_stream", raise_invalid)

    response = client.post(
        "/streams/camera-01/start",
        json={"stream_key": "invalid"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid stream key"
