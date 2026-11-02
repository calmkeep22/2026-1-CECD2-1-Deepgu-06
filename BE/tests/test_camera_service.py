from types import SimpleNamespace

import pytest

from app.core.exceptions import AppException
from app.schemas.camera import CameraUpdateRequest
from app.services.camera_service import CameraService


def test_running_camera_stream_key_cannot_be_changed(db):
    camera = SimpleNamespace(
        id=100,
        stream_key="stream-01",
        status="RUNNING",
        updated_at=None,
    )
    db.query.return_value.filter.return_value.first.return_value = None
    payload = CameraUpdateRequest(streamKey="stream-02")

    with pytest.raises(AppException) as exc_info:
        CameraService.update_camera(db, camera, payload)

    assert exc_info.value.code == "CANNOT_UPDATE_STREAM_KEY_WHILE_RUNNING"
    assert camera.stream_key == "stream-01"
    db.commit.assert_not_called()


def test_empty_camera_update_is_rejected(db):
    camera = SimpleNamespace(id=100, status="STOPPED")
    payload = CameraUpdateRequest()

    with pytest.raises(AppException) as exc_info:
        CameraService.update_camera(db, camera, payload)

    assert exc_info.value.code == "INVALID_REQUEST"
    db.commit.assert_not_called()
