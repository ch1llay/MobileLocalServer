from fastapi import Depends, Header, HTTPException, status

from app.config import get_settings
from app.services.auth import AuthService
from app.services.upload import UploadService


def get_settings_dep():
    return get_settings()


def get_auth_service(settings=Depends(get_settings_dep)) -> AuthService:
    return AuthService(settings)


def get_upload_service(settings=Depends(get_settings_dep)) -> UploadService:
    upload_dir = settings.get_upload_dir_resolved()
    return UploadService(upload_dir)


def current_user_from_token(
    authorization: str | None = Header(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )
    token = authorization[7:].strip()
    if not auth_service.verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
