from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import AppException
from app.schemas.stream import MediaStartData, MediaStartResponse, StreamCallbackRequest
from app.services.stream_service import StreamService


def make_camera(status="STOPPED", active=True):
    return SimpleNamespace(
        id=100,
        camera_id="camera-01",
        stream_key="stream-01",
        status=status,
        active=active,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_start_stream_saves_session_after_media_start(db, monkeypatch):
    service = StreamService(db)
    camera = make_camera()
    monkeypatch.setattr(service, "_get_camera_or_404", lambda camera_id: camera)
    monkeypatch.setattr(service, "_get_latest_session", lambda camera_id: None)
    service.media_client.start_stream = AsyncMock(
        return_value=MediaStartResponse(
            success=True,
            data=MediaStartData(status="STARTING", hls_url="/live/stream-01/index.m3u8"),
        )
    )

    def assign_session_id(session):
        session.id = 501

    db.refresh.side_effect = assign_session_id

    result = await service.start_stream("camera-01")

    assert result.camera_id == "camera-01"
    assert result.status == "STARTING"
    assert result.session_id == 501
    assert camera.status == "STARTING"
    db.add.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_start_stream_stops_media_when_database_commit_fails(db, monkeypatch):
    service = StreamService(db)
    camera = make_camera()
    monkeypatch.setattr(service, "_get_camera_or_404", lambda camera_id: camera)
    monkeypatch.setattr(service, "_get_latest_session", lambda camera_id: None)
    service.media_client.start_stream = AsyncMock(
        return_value=MediaStartResponse(
            success=True,
            data=MediaStartData(status="STARTING", hls_url="/live/stream-01/index.m3u8"),
        )
    )
    service.media_client.stop_stream = AsyncMock()
    db.commit.side_effect = SQLAlchemyError("database unavailable")

    with pytest.raises(AppException) as exc_info:
        await service.start_stream("camera-01")

    assert exc_info.value.code == "DATABASE_ERROR"
    db.rollback.assert_called_once()
    service.media_client.stop_stream.assert_awaited_once()


def test_callback_updates_camera_and_latest_session(db, monkeypatch):
    service = StreamService(db)
    camera = make_camera(status="STARTING")
    session = SimpleNamespace(
        status="STARTING",
        updated_at=None,
        stopped_at=None,
    )
    monkeypatch.setattr(service, "_get_camera_or_404", lambda camera_id: camera)
    monkeypatch.setattr(service, "_get_latest_session", lambda camera_id: session)

    service.handle_callback(
        StreamCallbackRequest(
            camera_id="camera-01",
            status="RUNNING",
            hls_url="/live/stream-01/index.m3u8",
        )
    )

    assert camera.status == "RUNNING"
    assert session.status == "RUNNING"
    assert session.stopped_at is None
    db.commit.assert_called_once()
