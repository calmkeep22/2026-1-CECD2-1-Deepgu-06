from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_admin
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models.user import User
from app.schemas.camera import CameraCreateRequest, CameraUpdateRequest
from app.services.camera_access_policy import CameraAccessPolicy
from app.services.camera_service import CameraService
from app.utils.response import success_response


router = APIRouter(prefix="/api/cameras", tags=["Cameras"])


def serialize_camera_list_item(camera):
    return {
        "id": camera.id,
        "cameraId": camera.camera_id,
        "name": camera.name,
        "location": camera.location,
        "status": camera.status,
        "active": camera.active,
    }


def serialize_camera_detail(camera):
    return {
        "id": camera.id,
        "cameraId": camera.camera_id,
        "name": camera.name,
        "location": camera.location,
        "streamKey": camera.stream_key,
        "description": camera.description,
        "status": camera.status,
        "active": camera.active,
        "createdAt": camera.created_at,
        "updatedAt": camera.updated_at,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_camera(
    payload: CameraCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    camera = CameraService.create_camera(db, payload)
    return success_response(data=serialize_camera_detail(camera))


@router.get("")
def get_cameras(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access_policy = CameraAccessPolicy(db, current_user)
    allowed_camera_ids = access_policy.get_allowed_camera_ids()
    if allowed_camera_ids is None:
        cameras = CameraService.get_camera_list(db)
    else:
        cameras = CameraService.get_camera_list_by_camera_ids(db, allowed_camera_ids)

    return success_response(data=[serialize_camera_list_item(c) for c in cameras])


@router.get("/{cameraId}")
def get_camera(
    cameraId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    access_policy = CameraAccessPolicy(db, current_user)
    camera = access_policy.get_camera(cameraId)
    if not camera:
        raise AppException(status_code=404, code="CAMERA_NOT_FOUND", message="카메라를 찾을 수 없습니다.")

    if not access_policy.can_access(camera):
        raise AppException(status_code=403, code="ACCESS_DENIED", message="접근 권한이 없습니다.")

    return success_response(data=serialize_camera_detail(camera))


@router.patch("/{cameraId}")
def update_camera(
    cameraId: str,
    payload: CameraUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    camera = CameraService.get_camera_by_camera_id(db, cameraId)
    if not camera:
        raise AppException(status_code=404, code="CAMERA_NOT_FOUND", message="카메라를 찾을 수 없습니다.")

    updated_camera = CameraService.update_camera(db, camera, payload)
    return success_response(data=serialize_camera_detail(updated_camera))


@router.delete("/{cameraId}")
def delete_camera(
    cameraId: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    camera = CameraService.get_camera_by_camera_id(db, cameraId)
    if not camera:
        raise AppException(status_code=404, code="CAMERA_NOT_FOUND", message="카메라를 찾을 수 없습니다.")

    CameraService.delete_camera(db, camera)
    return success_response(data={"cameraId": cameraId, "deleted": True})
