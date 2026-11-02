import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("DB_HOST", "127.0.0.1")
os.environ.setdefault("DB_PORT", "3307")
os.environ.setdefault("DB_NAME", "deepgu_test")
os.environ.setdefault("DB_USER", "deepgu_test")
os.environ.setdefault("DB_PASSWORD", "deepgu_test_password")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CALLBACK_SECRET", "test-callback-secret")

from app.core.auth import get_current_user, require_admin  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def db():
    return MagicMock(name="db_session")


@pytest.fixture
def admin_user():
    return SimpleNamespace(
        id=1,
        email="admin@example.com",
        name="Admin",
        role="ADMIN",
        status="ACTIVE",
    )


@pytest.fixture
def normal_user():
    return SimpleNamespace(
        id=2,
        email="user@example.com",
        name="User",
        role="USER",
        status="ACTIVE",
    )


@pytest.fixture
def client(db, admin_user):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[require_admin] = lambda: admin_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
