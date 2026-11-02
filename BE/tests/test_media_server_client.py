import httpx
import pytest

from app.clients.media_server_client import MediaServerClient
from app.core.exceptions import AppException
from app.schemas.stream import MediaStartRequest


@pytest.mark.asyncio
async def test_media_client_parses_successful_start_response(respx_mock):
    client = MediaServerClient()
    respx_mock.post(f"{client.base_url}/streams/camera-01/start").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "status": "STARTING",
                    "hls_url": "/live/stream-01/index.m3u8",
                },
            },
        )
    )

    response = await client.start_stream(
        MediaStartRequest(
            camera_id="camera-01",
            stream_key="stream-01",
            callback_url="http://backend/internal/streams/callback",
        )
    )

    assert response.success is True
    assert response.data.status == "STARTING"
    assert response.data.hls_url == "/live/stream-01/index.m3u8"


@pytest.mark.asyncio
async def test_media_client_maps_timeout_to_gateway_error(respx_mock):
    client = MediaServerClient()
    respx_mock.post(f"{client.base_url}/streams/camera-01/start").mock(
        side_effect=httpx.ConnectTimeout("media server timeout")
    )

    with pytest.raises(AppException) as exc_info:
        await client.start_stream(
            MediaStartRequest(camera_id="camera-01", stream_key="stream-01")
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.code == "MEDIA_SERVER_START_FAILED"


@pytest.mark.asyncio
async def test_media_client_rejects_success_false_response(respx_mock):
    client = MediaServerClient()
    respx_mock.post(f"{client.base_url}/streams/camera-01/start").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": False,
                "data": {
                    "status": "FAILED",
                    "hls_url": "/live/stream-01/index.m3u8",
                },
            },
        )
    )

    with pytest.raises(AppException) as exc_info:
        await client.start_stream(
            MediaStartRequest(camera_id="camera-01", stream_key="stream-01")
        )

    assert exc_info.value.code == "MEDIA_SERVER_START_FAILED"
