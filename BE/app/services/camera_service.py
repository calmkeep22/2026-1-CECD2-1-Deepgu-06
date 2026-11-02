from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.models.camera import Camera
from app.schemas.camera import CameraCreateRequest, CameraUpdateRequest


class CameraService:
    @staticmethod
    def get_camera_by_camera_id(db: Session, camera_id: str) -> Camera | None:
        return db.query(Camera).filter(Camera.camera_id == camera_id).first()

    @staticmethod
    def get_camera_by_stream_key(db: Session, stream_key: str) -> Camera | None:
        return db.query(Camera).filter(Camera.stream_key == stream_key).first()

    @staticmethod
    def create_camera(db: Session, payload: CameraCreateRequest) -> Camera:
        existing_camera_id = CameraService.get_camera_by_camera_id(db, payload.cameraId)
        if existing_camera_id:
            raise AppException(
                status_code=409,
                code="CAMERA_ID_ALREADY_EXISTS",
                message="이미 사용 중인 카메라 ID입니다.",
            )
        existing_stream_key = CameraService.get_camera_by_stream_key(db, payload.streamKey)
        if existing_stream_key:
            raise AppException(
                status_code=409,
                code="STREAM_KEY_ALREADY_EXISTS",
                message="존재하는 스트리밍 키입니다.",
            )
        now = datetime.utcnow()

        camera = Camera(
            camera_id=payload.cameraId,
            name=payload.name,
            location=payload.location,
            stream_key=payload.streamKey,
            description=payload.description,
            status="INACTIVE",
            active=True,
            created_at=now,
            updated_at=now,
        )

        try:
            db.add(camera)
            db.commit()
            db.refresh(camera)
            return camera
        except IntegrityError:
            db.rollback()
            raise AppException(
                status_code=409,
                code="DATABASE_INTEGRITY_ERROR",
                message="데이터베이스 무결성 오류입니다.",
            )

    @staticmethod
    def get_camera_list(db: Session) -> list[Camera]:
        return db.query(Camera).order_by(Camera.id.desc()).all()

    @staticmethod
    def get_camera_list_by_camera_ids(db: Session, camera_ids: list[str]) -> list[Camera]:
        if not camera_ids:
            return []
        return db.query(Camera).filter(Camera.camera_id.in_(camera_ids)).order_by(Camera.id.desc()).all()

    @staticmethod
    def update_camera(db: Session, camera: Camera, payload: CameraUpdateRequest) -> Camera:
        update_fields = payload.model_dump(exclude_unset=True)

        if not update_fields:
            raise AppException(
                status_code=400,
                code="INVALID_REQUEST",
                message="수정할 항목이 없습니다.",
            )

        if "name" in update_fields and update_fields["name"] is None:
            raise AppException(
                status_code=400,
                code="INVALID_REQUEST",
                message="카메라 이름은 비워둘 수 없습니다.",
            )

        if "streamKey" in update_fields and update_fields["streamKey"] is None:
            raise AppException(
                status_code=400,
                code="INVALID_REQUEST",
                message="스트리밍 키는 비워둘 수 없습니다.",
            )

        if "streamKey" in update_fields:
            duplicated_stream_key = (
                db.query(Camera)
                .filter(
                    Camera.stream_key == update_fields["streamKey"],
                    Camera.id != camera.id,
                )
                .first()
            )
            if duplicated_stream_key:
                raise AppException(
                    status_code=409,
                    code="STREAM_KEY_ALREADY_EXISTS",
                    message="존재하는 스트리밍 키입니다.",
                )

        if "name" in update_fields:
            camera.name = update_fields["name"]

        if "location" in update_fields:
            camera.location = update_fields["location"]

        if "streamKey" in update_fields:
            if camera.status == "RUNNING":
                raise AppException(
                    status_code=409,
                    code="CANNOT_UPDATE_STREAM_KEY_WHILE_RUNNING",
                    message="실행 중인 카메라의 스트리밍 키는 변경할 수 없습니다.",
                )
            camera.stream_key = update_fields["streamKey"]

        if "description" in update_fields:
            camera.description = update_fields["description"]

        camera.updated_at = datetime.utcnow()

        try:
            db.commit()
            db.refresh(camera)
            return camera
        except IntegrityError:
            db.rollback()
            raise AppException(
                status_code=409,
                code="DATABASE_INTEGRITY_ERROR",
                message="데이터베이스 무결성 오류입니다.",
            )

    @staticmethod
    def delete_camera(db: Session, camera: Camera) -> None:
        if camera.status == "RUNNING":
            raise AppException(
                status_code=409,
                code="CAMERA_RUNNING_CANNOT_DELETE",
                message="실행 중인 카메라는 삭제할 수 없습니다.",
            )

        try:
            db.delete(camera)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise AppException(
                status_code=409,
                code="DATABASE_INTEGRITY_ERROR",
                message="데이터베이스 무결성 오류입니다.",
            )
