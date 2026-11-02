from datetime import datetime
from types import SimpleNamespace

from app.api import camera as camera_api
from app.core.auth import get_current_user
from app.main import app


def make_camera():
    now = datetime(2026, 1, 1, 12, 0, 0)
    return SimpleNamespace(
        id=100,
        camera_id="camera-01",
        name="Lobby",
        location=None,
        stream_key="stream-01",
        description=None,
        status="INACTIVE",
        active=True,
        created_at=now,
        updated_at=now,
    )


def test_admin_can_create_camera(client, monkeypatch):
    camera = make_camera()
    monkeypatch.setattr(
        camera_api.CameraService,
        "create_camera",
        lambda db, payload: camera,
    )

    response = client.post(
        "/api/cameras",
        json={
            "cameraId": "CAMERA-01",
            "name": " Lobby ",
            "location": "",
            "streamKey": "STREAM-01",
            "description": "",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["cameraId"] == "camera-01"
    assert response.json()["data"]["location"] is None


def test_duplicate_camera_id_returns_conflict(client, monkeypatch):
    def raise_duplicate(db, payload):
        raise ValueError("CAMERA_ID_ALREADY_EXISTS")

    monkeypatch.setattr(camera_api.CameraService, "create_camera", raise_duplicate)

    response = client.post(
        "/api/cameras",
        json={
            "cameraId": "camera-01",
            "name": "Lobby",
            "streamKey": "stream-01",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "CAMERA_ID_ALREADY_EXISTS"


def test_unassigned_user_cannot_read_camera(client, db, normal_user, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: normal_user
    monkeypatch.setattr(
        camera_api.CameraService,
        "get_camera_by_camera_id",
        lambda db, camera_id: make_camera(),
    )
    db.query.return_value.filter.return_value.first.return_value = None

    response = client.get("/api/cameras/camera-01")

    assert response.status_code == 403
    assert response.json()["detail"] == "ACCESS_DENIED"
