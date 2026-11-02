from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api import camera as camera_api
from app.core.auth import get_current_user
from app.core.exceptions import AppException
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
        raise AppException(
            status_code=409,
            code="CAMERA_ID_ALREADY_EXISTS",
            message="이미 사용 중인 카메라 ID입니다.",
        )

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
    assert response.json()["error"]["code"] == "CAMERA_ID_ALREADY_EXISTS"


def test_unassigned_user_cannot_read_camera(client, db, normal_user, monkeypatch):
    app.dependency_overrides[get_current_user] = lambda: normal_user
    camera_query = MagicMock()
    camera_query.filter.return_value.first.return_value = make_camera()
    assignment_query = MagicMock()
    assignment_query.filter.return_value.first.return_value = None
    db.query.side_effect = [camera_query, assignment_query]

    response = client.get("/api/cameras/camera-01")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
