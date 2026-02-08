from starlette.requests import Request

from fastapi import Depends, HTTPException, status

from app.config import get_settings
from app.services.auth import AuthService
from app.services.upload import UploadService
from app.services.upload_codes import UploadCodesService


def get_settings_dep():
    return get_settings()


def get_auth_service(settings=Depends(get_settings_dep)) -> AuthService:
    return AuthService(settings)


def get_upload_service(settings=Depends(get_settings_dep)) -> UploadService:
    upload_dir = settings.get_upload_dir_resolved()
    return UploadService(upload_dir, settings.user_quota_bytes)


def get_upload_codes_service(settings=Depends(get_settings_dep)) -> UploadCodesService:
    return UploadCodesService(settings.codes_file)


def _extract_token(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.query_params.get("token")


def verify_token(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """Extract token from Authorization header or query param 'token'; raise 401 if missing or invalid."""
    token = _extract_token(request)
    if not token or not auth_service.verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )


def current_user_from_token(
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> None:
    """Alias for verify_token for use as dependency on protected endpoints."""
    verify_token(request, auth_service)
