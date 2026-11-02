from datetime import datetime
from unittest.mock import MagicMock

from app.clients import s3_client


def test_upload_event_video_uses_configured_bucket(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(s3_client, "_get_client", lambda: client)
    monkeypatch.setattr(s3_client.settings, "s3_bucket_name", "test-bucket")

    key = s3_client.upload_event_video(
        b"video-bytes",
        "camera-01",
        datetime(2026, 10, 28, 12, 0, 0),
    )

    assert key.startswith("events/camera-01/2026/10/")
    assert key.endswith(".mp4")
    client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=key,
        Body=b"video-bytes",
        ContentType="video/mp4",
    )


def test_presigned_url_is_skipped_without_bucket(monkeypatch):
    monkeypatch.setattr(s3_client.settings, "s3_bucket_name", "")
    client = MagicMock()
    monkeypatch.setattr(s3_client, "_get_client", lambda: client)

    result = s3_client.generate_presigned_url("events/camera-01/video.mp4")

    assert result is None
    client.generate_presigned_url.assert_not_called()
