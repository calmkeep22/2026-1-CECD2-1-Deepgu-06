from sqlalchemy.orm import Session

from app.models.camera import Camera
from app.models.camera_assignment import CameraAssignment
from app.models.user import User


class CameraAccessPolicy:
    """Resolve the cameras a user may access.

    Raising errors is left to the API layer; this class only answers
    which cameras are accessible.
    """

    def __init__(self, db: Session, user: User):
        self.db = db
        self.user = user

    @property
    def allows_all(self) -> bool:
        return self.user.role == "ADMIN"

    def get_camera(self, camera_id: str) -> Camera | None:
        return self.db.query(Camera).filter(Camera.camera_id == camera_id).first()

    def can_access(self, camera: Camera) -> bool:
        if self.allows_all:
            return True

        return (
            self.db.query(CameraAssignment.id)
            .filter(
                CameraAssignment.user_id == self.user.id,
                CameraAssignment.camera_id == camera.id,
            )
            .first()
            is not None
        )

    def get_allowed_camera_ids(self) -> list[str] | None:
        """Return external camera IDs, or None when the user may access all."""
        if self.allows_all:
            return None

        rows = (
            self.db.query(Camera.camera_id)
            .join(CameraAssignment, CameraAssignment.camera_id == Camera.id)
            .filter(CameraAssignment.user_id == self.user.id)
            .all()
        )
        return [camera_id for (camera_id,) in rows]
