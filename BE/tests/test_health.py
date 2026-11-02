import importlib


main_module = importlib.import_module("app.main")


def test_health_returns_running_status(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "server is running",
        "data": {"app": "ok"},
    }


def test_ready_returns_503_when_database_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(main_module, "check_db_connection", lambda: False)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["data"]["database"] == "fail"
