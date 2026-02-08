import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import logger
from app.config import get_settings
from app.dependencies import (
    current_user_from_token,
    get_auth_service,
    get_upload_codes_service,
    get_upload_service,
)
from app.services.auth import AuthService
from app.services.upload import FileSizeExceededError, QuotaExceededError, UploadService
from app.services.upload_codes import UploadCodesService

router = APIRouter()


class LoginBody(BaseModel):
    password: str = ""


class CreateUserBody(BaseModel):
    name: str = ""


class VerifyCodeBody(BaseModel):
    pin: str = ""


class SettingsUpdateBody(BaseModel):
    parallel_upload: bool = False


def _get_settings_path():
    return get_settings().codes_file.resolve().parent / "settings.json"


def _read_app_settings() -> dict:
    """Return app settings from data/settings.json; default parallel_upload false."""
    path = _get_settings_path()
    if not path.exists():
        return {"parallel_upload": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"parallel_upload": bool(data.get("parallel_upload", False))}
    except (json.JSONDecodeError, OSError):
        return {"parallel_upload": False}


def _write_app_settings(data: dict) -> None:
    path = _get_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.post("/login")
async def login(
    body: LoginBody,
    auth_service: AuthService = Depends(get_auth_service),
):
    if not auth_service.verify_pin(body.password):
        logger.warning("Login failed: invalid password")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
    token = auth_service.create_session_token()
    return {"token": token}


@router.post("/verify-code")
async def verify_code(
    body: VerifyCodeBody,
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    """Verify PIN/code and return user name for greeting. No token."""
    name = codes_service.get_name_by_code(body.pin)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired code",
        )
    return {"name": name}


@router.get("/settings")
async def get_public_settings():
    """Public settings for upload page (e.g. parallel_upload)."""
    return _read_app_settings()


@router.get("/admin/settings")
async def get_admin_settings(
    _: None = Depends(current_user_from_token),
):
    """Admin: read app settings."""
    return _read_app_settings()


@router.post("/admin/settings")
async def update_admin_settings(
    body: SettingsUpdateBody,
    _: None = Depends(current_user_from_token),
):
    """Admin: update app settings (e.g. parallel_upload)."""
    data = _read_app_settings()
    data["parallel_upload"] = body.parallel_upload
    _write_app_settings(data)
    return data


@router.get("/my-files")
async def list_my_files(
    pin: str = Query(..., description="User PIN"),
    upload_service: UploadService = Depends(get_upload_service),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    """List files in the current user's folder (identified by PIN)."""
    name = codes_service.get_name_by_code(pin)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired code",
        )
    files = upload_service.list_files_in_folder(name)
    return {"files": files}


@router.get("/my-files/files/{filename:path}")
async def download_my_file(
    filename: str,
    pin: str = Query(..., description="User PIN"),
    upload_service: UploadService = Depends(get_upload_service),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    """Download a file from the current user's folder (identified by PIN)."""
    name = codes_service.get_name_by_code(pin)
    if not name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired code",
        )
    try:
        file_path = upload_service.get_file_path_in_folder(name, filename)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.get("/files")
async def list_files(
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
):
    return {"files": upload_service.list_files()}


async def _chunk_iter(upload_file: UploadFile, chunk_size: int) -> AsyncIterator[bytes]:
    while True:
        chunk = await upload_file.read(chunk_size)
        if not chunk:
            break
        yield chunk


@router.post("/upload")
async def upload_file(
    upload_service: UploadService = Depends(get_upload_service),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
    file: UploadFile = File(...),
    pin: str = Form(..., description="Upload PIN (from admin)"),
):
    sender_name = codes_service.get_name_by_code(pin)
    if not sender_name:
        logger.warning("Upload rejected: invalid PIN")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired PIN",
        )
    settings = get_settings()
    max_bytes = settings.max_upload_bytes
    filename = file.filename or "unnamed"
    chunk_size = 1024 * 1024
    try:
        name = await upload_service.save_file_streaming(
            filename,
            _chunk_iter(file, chunk_size),
            max_bytes,
            sender_name=sender_name,
        )
        return {"filename": name}
    except FileSizeExceededError:
        logger.warning("Upload rejected: file exceeds maximum size")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size ({settings.max_upload_mb} MB)",
        )
    except QuotaExceededError:
        logger.warning("Upload rejected: folder quota exceeded")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Folder quota exceeded (max {settings.user_quota_gb} GB)",
        )
    except ValueError as e:
        logger.warning("Upload rejected: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/admin/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserBody,
    _: None = Depends(current_user_from_token),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    if not body.name or not body.name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name is required",
        )
    try:
        pin, _, created_at = codes_service.create_code(body.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    logger.info("Admin created upload user")
    return {"pin": pin, "name": body.name.strip(), "created_at": created_at}


@router.get("/admin/users")
async def list_admin_users(
    _: None = Depends(current_user_from_token),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    users = codes_service.list_users()
    return {
        "users": [
            {"label": u["label"], "created_at": u["created_at"], "index": i}
            for i, u in enumerate(users)
        ]
    }


@router.delete("/admin/users/{index}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    index: int,
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
    codes_service: UploadCodesService = Depends(get_upload_codes_service),
):
    label = codes_service.delete_user_by_index(index)
    if label is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    upload_service.delete_folder(label)


@router.get("/files/{path:path}")
async def download_file(
    path: str,
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
):
    try:
        file_path = upload_service.get_file_path(path)
    except (ValueError, FileNotFoundError):
        logger.info("Download: file not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    # Safe download: octet-stream to avoid MIME sniffing; filename in Content-Disposition
    return FileResponse(
        path=file_path,
        filename=file_path.name,
        media_type="application/octet-stream",
    )


@router.delete("/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    path: str,
    _: None = Depends(current_user_from_token),
    upload_service: UploadService = Depends(get_upload_service),
):
    try:
        upload_service.delete_file(path)
    except (ValueError, FileNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
