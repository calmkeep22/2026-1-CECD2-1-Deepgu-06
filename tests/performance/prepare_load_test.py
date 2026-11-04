import argparse
import base64
import hashlib
from datetime import UTC, datetime

import bcrypt
import httpx
import pymysql


EMAIL = "loadtest@example.com"
PASSWORD = "loadtest-password"
CAMERA_PREFIX = "load-camera-"


def db_connection():
    return pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="deepgu_test",
        password="deepgu_test_password",
        database="deepgu_test",
        autocommit=True,
    )


def password_hash(password: str) -> str:
    prepared = base64.b64encode(hashlib.sha256(password.encode()).digest())
    return bcrypt.hashpw(prepared, bcrypt.gensalt()).decode()


def cleanup() -> None:
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM cameras WHERE camera_id LIKE %s", (f"{CAMERA_PREFIX}%",))
            camera_pks = [row[0] for row in cursor.fetchall()]
            for camera_pk in camera_pks:
                cursor.execute("DELETE FROM stream_sessions WHERE camera_id = %s", (camera_pk,))
                cursor.execute("DELETE FROM camera_assignments WHERE camera_id = %s", (camera_pk,))
                cursor.execute("DELETE FROM cameras WHERE id = %s", (camera_pk,))
            cursor.execute("DELETE FROM users WHERE email = %s", (EMAIL,))


def setup(stream_count: int) -> None:
    cleanup()
    now = datetime.now(UTC).replace(tzinfo=None)

    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users
                    (email, password_hash, name, role, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'ADMIN', 'ACTIVE', %s, %s)
                """,
                (EMAIL, password_hash(PASSWORD), "Load Test Admin", now, now),
            )

    with httpx.Client(base_url="http://127.0.0.1:18000", timeout=10.0) as client:
        login = client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
        login.raise_for_status()
        token = login.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        for index in range(1, stream_count + 1):
            camera_id = f"{CAMERA_PREFIX}{index}"
            stream_key = f"load-stream-{index}"
            created = client.post(
                "/api/cameras",
                headers=headers,
                json={
                    "cameraId": camera_id,
                    "name": f"Load Camera {index}",
                    "location": "Local load test",
                    "streamKey": stream_key,
                },
            )
            created.raise_for_status()
            started = client.post(f"/api/cameras/{camera_id}/stream/start", headers=headers)
            started.raise_for_status()

    print(f"prepared {stream_count} cameras")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("setup", "cleanup"))
    parser.add_argument("--stream-count", type=int, default=3)
    args = parser.parse_args()

    if args.action == "setup":
        setup(args.stream_count)
    else:
        cleanup()
        print("load test data cleaned")


if __name__ == "__main__":
    main()

