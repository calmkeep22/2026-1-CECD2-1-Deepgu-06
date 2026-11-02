import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


os.environ.setdefault("CALLBACK_SECRET", "test-callback-secret")

from app.api.health import router as health_router
from app.api.stream import router as stream_router
from app.services import hls_service


@pytest.fixture(autouse=True)
def clear_stream_registry():
    with hls_service._lock:
        hls_service._registry.clear()
    yield
    with hls_service._lock:
        hls_service._registry.clear()


@pytest.fixture
def client():
    test_app = FastAPI()
    test_app.include_router(health_router)
    test_app.include_router(stream_router)

    with TestClient(test_app) as test_client:
        yield test_client
