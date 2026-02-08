from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.requests import Request

from app.config import get_settings
from app.dependencies import (
    current_user_from_token,
    get_auth_service,
    get_upload_service,
)
from app.services.auth import AuthService
from app.services.upload import UploadService

router = APIRouter()


class LoginBody(BaseModel):
    pin: str = ""


def _verify_token_from_request(
    request: Request,
    auth_service: AuthService,
) -> None:
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.query_params.get("token")
    if not token or not auth_service.verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid token",
        )


@router.post("/login")
async def login(
    body: LoginBody,
    auth_service: AuthService = Depends(get_auth_service),
):
    if not auth_service.verify_pin(body.pin):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid PIN")
    token = auth_service.create_session_token()
    return {"token": token}


@router.get("/files")
async def list_files(
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
):
    return {"files": upload_service.list_files()}


@router.post("/upload")
async def upload_file(
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
    file: UploadFile = File(...),
):
    settings = get_settings()
    max_bytes = settings.max_upload_bytes
    filename = file.filename or "unnamed"
    chunk_size = 1024 * 1024
    chunks = []
    total = 0
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds maximum size ({settings.max_upload_mb} MB)",
            )
        chunks.append(chunk)
    try:
        name = upload_service.save_file(BytesIO(b"".join(chunks)), filename)
        return {"filename": name}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/files/{path:path}")
async def download_file(
    request: Request,
    path: str,
    auth_service: AuthService = Depends(get_auth_service),
    upload_service: UploadService = Depends(get_upload_service),
):
    _verify_token_from_request(request, auth_service)
    try:
        file_path = upload_service.get_file_path(path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    # Safe download: octet-stream to avoid MIME sniffing; filename in Content-Disposition
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )
