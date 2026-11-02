import base64
import hashlib
import os
import uuid
from datetime import datetime

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


def test_backend_controls_media_server_stream_lifecycle():
    suffix = uuid.uuid4().hex[:8]
    email = f"integration-{suffix}@example.com"
    password = "integration-password"
    camera_id = f"camera-{suffix}"
    stream_key = f"stream-{suffix}"

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users
                    (email, password_hash, name, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'ADMIN', 'ACTIVE', %s, %s)
                """,
                (email, _password_hash(password), "Integration Admin", datetime.utcnow(), datetime.utcnow()),
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

            start_response = client.post(
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream/start",
                headers=headers,
            )
            assert start_response.status_code == 200
            assert start_response.json()["data"]["status"] in {"STARTING", "RUNNING"}

            media_status = client.get(f"{MEDIA_URL}/streams/{camera_id}")
            assert media_status.status_code == 200
            assert media_status.json()["data"]["status"] in {"STARTING", "RUNNING"}

            stop_response = client.post(
                f"{BACKEND_URL}/api/cameras/{camera_id}/stream/stop",
                headers=headers,
            )
            assert stop_response.status_code == 200
            assert stop_response.json()["data"]["status"] == "STOPPED"
    finally:
        with _db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM cameras WHERE camera_id = %s", (camera_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("DELETE FROM stream_sessions WHERE camera_id = %s", (row[0],))
                    cursor.execute("DELETE FROM camera_assignments WHERE camera_id = %s", (row[0],))
                    cursor.execute("DELETE FROM cameras WHERE id = %s", (row[0],))
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
