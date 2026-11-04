import base64
import hashlib
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter, sleep

import bcrypt
import httpx
import pymysql
import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 after starting compose.test.yml",
    ),
]

BACKEND_URL = os.getenv("TEST_BACKEND_URL", "http://127.0.0.1:18000")
MEDIA_URL = os.getenv("TEST_MEDIA_URL", "http://127.0.0.1:19000")
HLS_URL = os.getenv("TEST_HLS_URL", "http://127.0.0.1:18888")
STREAM_KEY = os.getenv("TEST_STREAM_KEY", "integration-stream")

START_API_MAX_SECONDS = float(os.getenv("TEST_START_API_MAX_SECONDS", "5"))
RUNNING_MAX_SECONDS = float(os.getenv("TEST_RUNNING_MAX_SECONDS", "20"))
HLS_MAX_SECONDS = float(os.getenv("TEST_HLS_MAX_SECONDS", "20"))
STOP_API_MAX_SECONDS = float(os.getenv("TEST_STOP_API_MAX_SECONDS", "5"))

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = Path(
    os.getenv("TEST_COMPOSE_FILE", str(REPOSITORY_ROOT / "compose.test.yml"))
).resolve()


def _password_hash(password: str) -> str:
    prepared = base64.b64encode(hashlib.sha256(password.encode()).digest())
    return bcrypt.hashpw(prepared, bcrypt.gensalt()).decode()


def _db_connection():
    return pymysql.connect(
        host=os.getenv("TEST_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("TEST_DB_PORT", "3307")),
        user=os.getenv("TEST_DB_USER", "deepgu_test"),
        password=os.getenv("TEST_DB_PASSWORD", "deepgu_test_password"),
        database=os.getenv("TEST_DB_NAME", "deepgu_test"),
        autocommit=True,
    )


def _start_video_publisher() -> None:
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(COMPOSE_FILE),
            "--profile",
            "streaming",
            "up",
            "-d",
            "--force-recreate",
            "stream-publisher",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )


def _wait_for_status(
    client,
    url: str,
    status_reader,
    expected: str,
    timeout: float,
    headers: dict[str, str] | None = None,
) -> float:
    started = perf_counter()
    last_status = None

    while perf_counter() - started < timeout:
        response = client.get(url, headers=headers)
        if response.status_code == 200:
            last_status = status_reader(response.json())
            if last_status == expected:
                return perf_counter() - started
        sleep(0.5)

    pytest.fail(
        f"{url} did not reach {expected!r} within {timeout:.1f}s "
        f"(last status: {last_status!r})"
    )


def _wait_for_hls_playlist(client, stream_key: str, timeout: float) -> float:
    playlist_url = f"{HLS_URL}/live/{stream_key}/index.m3u8"
    started = perf_counter()

    while perf_counter() - started < timeout:
        try:
            response = client.get(
                playlist_url,
                follow_redirects=True,
                timeout=5.0,
            )
        except httpx.TimeoutException:
            continue
        if response.status_code == 200 and response.text.startswith("#EXTM3U"):
            return perf_counter() - started
        sleep(0.5)

    pytest.fail(f"HLS playlist was not ready within {timeout:.1f}s: {playlist_url}")


def test_backend_controls_media_server_stream_lifecycle():
    suffix = uuid.uuid4().hex[:8]
    email = f"integration-{suffix}@example.com"
    password = "integration-password"
    camera_id = f"camera-{suffix}"
    stream_key = STREAM_KEY
    token = None
    headers = None
    now = datetime.now(UTC).replace(tzinfo=None)

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users
                    (email, password_hash, name, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'ADMIN', 'ACTIVE', %s, %s)
                """,
                (email, _password_hash(password), "Integration Admin", now, now),
            )
            user_id = cursor.lastrowid

    try:
        with httpx.Client(timeout=10.0) as client:
            assert client.get(f"{BACKEND_URL}/ready").status_code == 200
            assert client.get(f"{MEDIA_URL}/health").status_code == 200

            login_response = client.post(
                f"{BACKEND_URL}/api/auth/login",
                json={"email": email, "password": password},
            )
            assert login_response.status_code == 200
            token = login_response.json()["data"]["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            create_response = client.post(
                f"{BACKEND_URL}/api/cameras",
                headers=headers,
                json={
                    "cameraId": camera_id,
                    "name": "Integration Camera",
                    "streamKey": stream_key,
                },
            )
            assert create_response.status_code == 201

            start_started = perf_counter()
            start_response = client.post(
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream/start",
                headers=headers,
            )
            start_api_seconds = perf_counter() - start_started
            assert start_response.status_code == 200
            assert start_response.json()["data"]["status"] in {"STARTING", "RUNNING"}
            assert start_api_seconds <= START_API_MAX_SECONDS

            _start_video_publisher()

            media_running_seconds = _wait_for_status(
                client,
                f"{MEDIA_URL}/streams/{camera_id}",
                lambda body: body["data"]["status"],
                "RUNNING",
                RUNNING_MAX_SECONDS,
            )
            backend_running_seconds = _wait_for_status(
                client,
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream",
                lambda body: body["data"]["camera_status"],
                "RUNNING",
                RUNNING_MAX_SECONDS,
                headers,
            )
            hls_ready_seconds = _wait_for_hls_playlist(
                client,
                stream_key,
                HLS_MAX_SECONDS,
            )

            stop_started = perf_counter()
            stop_response = client.post(
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream/stop",
                headers=headers,
            )
            stop_api_seconds = perf_counter() - stop_started
            assert stop_response.status_code == 200
            assert stop_response.json()["data"]["status"] == "STOPPED"
            assert stop_api_seconds <= STOP_API_MAX_SECONDS

            _wait_for_status(
                client,
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream",
                lambda body: body["data"]["camera_status"],
                "STOPPED",
                5.0,
                headers,
            )
            _wait_for_status(
                client,
                f"{MEDIA_URL}/streams/{camera_id}",
                lambda body: body["data"]["status"],
                "STOPPED",
                5.0,
            )

            print(
                "integration timings: "
                f"start_api={start_api_seconds:.3f}s, "
                f"media_running={media_running_seconds:.3f}s, "
                f"backend_running={backend_running_seconds:.3f}s, "
                f"hls_ready={hls_ready_seconds:.3f}s, "
                f"stop_api={stop_api_seconds:.3f}s"
            )
    finally:
        if token and headers:
            try:
                httpx.post(
                    f"{BACKEND_URL}/api/cameras/{camera_id}/stream/stop",
                    headers=headers,
                    timeout=3.0,
                )
            except httpx.HTTPError:
                pass
        with _db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM cameras WHERE camera_id = %s", (camera_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("DELETE FROM stream_sessions WHERE camera_id = %s", (row[0],))
                    cursor.execute("DELETE FROM camera_assignments WHERE camera_id = %s", (row[0],))
                    cursor.execute("DELETE FROM cameras WHERE id = %s", (row[0],))
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
