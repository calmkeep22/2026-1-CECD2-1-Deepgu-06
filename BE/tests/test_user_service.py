from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.exceptions import AppException
from app.services.user_service import UserService


def test_approve_user_changes_pending_user_to_active(db):
    user = SimpleNamespace(id=10, status="PENDING", updated_at=None)
    db.get.return_value = user
    service = UserService(db)

    approved = service.approve(10)

    assert approved.status == "ACTIVE"
    assert approved.updated_at is not None
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(user)


def test_approve_user_rejects_already_active_user(db):
    db.get.return_value = SimpleNamespace(id=10, status="ACTIVE")
    service = UserService(db)

    with pytest.raises(AppException) as exc_info:
        service.approve(10)

    assert exc_info.value.code == "ALREADY_APPROVED"
    db.commit.assert_not_called()


def test_assign_camera_rejects_duplicate_assignment(db):
    camera = SimpleNamespace(id=20, camera_id="camera-01")
    user = SimpleNamespace(id=10)
    existing_assignment = SimpleNamespace(user_id=10, camera_id=20)

    camera_query = MagicMock()
    camera_query.filter.return_value.first.return_value = camera
    assignment_query = MagicMock()
    assignment_query.filter.return_value.first.return_value = existing_assignment
    db.query.side_effect = [camera_query, assignment_query]
    db.get.return_value = user
    service = UserService(db)

    with pytest.raises(AppException) as exc_info:
        service.assign_camera("camera-01", 10)

    assert exc_info.value.code == "ALREADY_ASSIGNED"
    db.add.assert_not_called()
    db.commit.assert_not_called()
