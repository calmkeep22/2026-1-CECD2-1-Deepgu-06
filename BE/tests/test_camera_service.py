from types import SimpleNamespace

import pytest

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

    with pytest.raises(ValueError, match="CANNOT_UPDATE_STREAM_KEY_WHILE_RUNNING"):
        CameraService.update_camera(db, camera, payload)

    assert camera.stream_key == "stream-01"
    db.commit.assert_not_called()


def test_empty_camera_update_is_rejected(db):
    camera = SimpleNamespace(id=100, status="STOPPED")
    payload = CameraUpdateRequest()

    with pytest.raises(ValueError, match="INVALID_REQUEST"):
        CameraService.update_camera(db, camera, payload)

    db.commit.assert_not_called()
