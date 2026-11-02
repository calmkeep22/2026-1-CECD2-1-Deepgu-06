from types import SimpleNamespace

from app.api import auth as auth_api
from app.core.auth import hash_password, verify_password


def test_password_hash_round_trip():
    password = "correct horse battery staple"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_login_returns_access_token_for_active_user(client, db, monkeypatch):
    user = SimpleNamespace(
        id=10,
        email="active@example.com",
        password_hash="stored-hash",
        role="USER",
        status="ACTIVE",
    )
    db.query.return_value.filter.return_value.first.return_value = user
    monkeypatch.setattr(auth_api, "verify_password", lambda plain, hashed: True)
    monkeypatch.setattr(auth_api, "create_access_token", lambda user_id, role: "signed-token")

    response = client.post(
        "/api/auth/login",
        json={"email": "active@example.com", "password": "password"},
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "access_token": "signed-token",
        "token_type": "bearer",
    }


def test_login_rejects_pending_user(client, db, monkeypatch):
    user = SimpleNamespace(
        id=11,
        email="pending@example.com",
        password_hash="stored-hash",
        role="USER",
        status="PENDING",
    )
    db.query.return_value.filter.return_value.first.return_value = user
    monkeypatch.setattr(auth_api, "verify_password", lambda plain, hashed: True)

    response = client.post(
        "/api/auth/login",
        json={"email": "pending@example.com", "password": "password"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PENDING_APPROVAL"


def test_login_rejects_invalid_credentials(client, db, monkeypatch):
    db.query.return_value.filter.return_value.first.return_value = None
    monkeypatch.setattr(auth_api, "verify_password", lambda plain, hashed: False)

    response = client.post(
        "/api/auth/login",
        json={"email": "missing@example.com", "password": "password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"
