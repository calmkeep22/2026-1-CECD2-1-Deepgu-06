from app.api import internal as internal_api


def test_stream_callback_rejects_invalid_secret(client, monkeypatch):
    monkeypatch.setattr(internal_api.settings, "callback_secret", "expected-secret")

    response = client.post(
        "/internal/streams/callback",
        headers={"X-Callback-Secret": "wrong-secret"},
        json={"camera_id": "camera-01", "status": "RUNNING"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_stream_callback_delegates_valid_payload(client, monkeypatch):
    handled = []
    monkeypatch.setattr(internal_api.settings, "callback_secret", "expected-secret")
    monkeypatch.setattr(
        internal_api.StreamService,
        "handle_callback",
        lambda self, payload: handled.append(payload),
    )

    response = client.post(
        "/internal/streams/callback",
        headers={"X-Callback-Secret": "expected-secret"},
        json={
            "camera_id": "camera-01",
            "status": "RUNNING",
            "hls_url": "/live/stream-01/index.m3u8",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert handled[0].camera_id == "camera-01"
    assert handled[0].status == "RUNNING"
