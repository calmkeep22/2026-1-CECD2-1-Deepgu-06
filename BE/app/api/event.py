import json

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.clients.s3_client import generate_presigned_url
from app.core.auth import _decode_token, get_current_user, require_admin
from app.core.broadcaster import subscribe
from app.core.database import get_db
from app.core.exceptions import AppException
from app.models.user import User
from app.schemas.event import EventDetail, EventItem, EventListResponse, EventStatusUpdateRequest
from app.services.camera_access_policy import CameraAccessPolicy
from app.services.event_service import EventService
from app.utils.response import success_response

router = APIRouter(prefix="/api/events", tags=["events"])


def _check_camera_access(access_policy: CameraAccessPolicy, camera_id: str) -> None:
    if access_policy.allows_all:
        return

    camera = access_policy.get_camera(camera_id)
    if not camera:
        raise AppException(status_code=404, code="CAMERA_NOT_FOUND", message="카메라를 찾을 수 없습니다.")
    if not access_policy.can_access(camera):
        raise AppException(status_code=403, code="ACCESS_DENIED", message="접근 권한이 없습니다.")


@router.get("/stream")
async def event_stream(
    camera_id: str = Query(...),
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    payload = _decode_token(token)
    user_id = int(payload.get("sub", 0))
    user = db.get(User, user_id)
    if not user or user.status != "ACTIVE":
        raise AppException(status_code=401, code="UNAUTHORIZED", message="인증이 필요합니다.")
    _check_camera_access(CameraAccessPolicy(db, user), camera_id)

    async def generator():
        async for event in subscribe(camera_id):
            yield {"data": json.dumps(event, ensure_ascii=False)}
    return EventSourceResponse(generator())


@router.get("", response_model=dict)
def list_events(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    camera_id: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    allowed = CameraAccessPolicy(db, current_user).get_allowed_camera_ids()
    if camera_id and allowed is not None and camera_id not in allowed:
        raise AppException(status_code=403, code="ACCESS_DENIED", message="접근 권한이 없습니다.")
    items, total = EventService.list_events(
        db, page=page, size=size, status=status, camera_id=camera_id, allowed_camera_ids=allowed
    )
    return success_response(
        EventListResponse(
            items=[EventItem.model_validate(e) for e in items],
            total=total,
            page=page,
            size=size,
        ).model_dump()
    )


@router.get("/{event_id}", response_model=dict)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = EventService.get(db, event_id)
    if not event:
        raise AppException(status_code=404, code="EVENT_NOT_FOUND", message="이벤트를 찾을 수 없습니다.")
    _check_camera_access(CameraAccessPolicy(db, current_user), event.camera_id)

    detail = EventDetail.model_validate(event)
    detail.video_url = generate_presigned_url(event.s3_key) if event.s3_key else None
    if event.thumbnail_s3_keys:
        try:
            keys = json.loads(event.thumbnail_s3_keys)
        except json.JSONDecodeError:
            keys = []
    else:
        keys = []
    detail.thumbnail_urls = [url for url in (generate_presigned_url(key) for key in keys) if url]
    return success_response(detail.model_dump())


@router.patch("/{event_id}/status", response_model=dict)
def update_event_status(
    event_id: int,
    payload: EventStatusUpdateRequest,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    event = EventService.get(db, event_id)
    if not event:
        raise AppException(status_code=404, code="EVENT_NOT_FOUND", message="이벤트를 찾을 수 없습니다.")
    updated = EventService.update_status(db, event, payload.status)
    return success_response(EventItem.model_validate(updated).model_dump())
