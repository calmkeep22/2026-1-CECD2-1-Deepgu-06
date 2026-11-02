import json
from datetime import datetime

import pytest

from app.core.exceptions import AppException
from app.models.event import Event
from app.schemas.event import EventCreateRequest
from app.services import event_service
from app.services.event_service import EventService


def test_create_event_payload_uploads_video_and_thumbnails(db, monkeypatch):
    payload = EventCreateRequest(
        camera_id="camera-01",
        detected_at=datetime(2026, 1, 1, 12, 0, 0),
        anomaly_type="fight",
        confidence=0.93,
        description="detected",
    )
    monkeypatch.setattr(
        event_service.s3_client,
        "upload_event_video",
        lambda *args: "videos/event.mp4",
    )
    thumbnail_keys = iter(["thumbs/1.jpg", "thumbs/2.jpg"])
    monkeypatch.setattr(
        event_service.s3_client,
        "upload_event_thumbnail",
        lambda *args: next(thumbnail_keys),
    )

    event = EventService.create_from_event_payload(
        db,
        payload,
        ai_event_id="ai-event-01",
        video_bytes=b"video",
        thumbnail_bytes_list=[b"thumb-1", b"", b"thumb-2"],
    )

    assert event.s3_key == "videos/event.mp4"
    assert json.loads(event.thumbnail_s3_keys) == ["thumbs/1.jpg", "thumbs/2.jpg"]
    assert event.ai_event_id == "ai-event-01"
    db.add.assert_called_once_with(event)
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(event)


def test_update_event_status_rejects_unknown_status(db):
    event = Event(status="UNREVIEWED")

    with pytest.raises(AppException) as exc_info:
        EventService.update_status(db, event, "UNKNOWN")

    assert exc_info.value.code == "INVALID_STATUS"
    db.commit.assert_not_called()


def test_update_event_status_commits_allowed_status(db):
    event = Event(status="UNREVIEWED")

    updated = EventService.update_status(db, event, "REVIEWED")

    assert updated.status == "REVIEWED"
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(event)
