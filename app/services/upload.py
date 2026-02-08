import re
import shutil
from pathlib import Path
from typing import AsyncIterator, BinaryIO


# Unsafe characters for filenames; keep alphanumeric, dots, hyphens, underscores
UNSAFE_FILENAME_RE = re.compile(r"[^\w.\- ]", re.UNICODE)

# Sender name (folder name): letters, digits, hyphen, underscore, space
SENDER_NAME_RE = re.compile(r"[^\w\s\-]", re.UNICODE)
SENDER_NAME_MIN_LEN = 1
SENDER_NAME_MAX_LEN = 64


class FileSizeExceededError(Exception):
    """Raised when uploaded content exceeds max_bytes during streaming save."""


class QuotaExceededError(Exception):
    """Raised when sender folder would exceed user quota."""


class UploadService:
    def __init__(self, upload_dir: Path, user_quota_bytes: int) -> None:
        self._upload_dir = upload_dir.resolve()
        self._user_quota_bytes = user_quota_bytes

    def _safe_join(self, relative_path: str) -> Path:
        """Resolve relative_path against upload_dir; raise if outside upload_dir."""
        base = self._upload_dir.resolve()
        path_str = relative_path.lstrip("/\\")
        parts = Path(path_str).parts
        if any(p == ".." for p in parts):
            raise ValueError("Path traversal not allowed")
        resolved = (base / Path(*parts)).resolve()
        try:
            resolved.relative_to(base)
        except ValueError:
            raise ValueError("Path outside upload directory")
        return resolved

    def _sanitize_filename(self, filename: str) -> str:
        """Return a safe basename (no path, no unsafe chars)."""
        name = Path(filename).name
        name = UNSAFE_FILENAME_RE.sub("_", name)
        if not name.strip():
            name = "unnamed"
        return name

    def _sanitize_sender_name(self, raw: str) -> str:
        """Return a safe folder name for sender; raise ValueError if invalid."""
        s = raw.strip()
        s = SENDER_NAME_RE.sub("_", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s or len(s) < SENDER_NAME_MIN_LEN or len(s) > SENDER_NAME_MAX_LEN:
            raise ValueError("Invalid sender name")
        return s

    def get_folder_size_bytes(self, sender_name: str) -> int:
        """Return total size of all files in the sender folder; 0 if folder missing or empty."""
        try:
            folder = self._safe_join(sender_name)
        except ValueError:
            return 0
        if not folder.is_dir():
            return 0
        total = 0
        try:
            for p in folder.iterdir():
                if p.is_file():
                    total += p.stat().st_size
        except OSError:
            pass
        return total

    def save_file(self, stream: BinaryIO, filename: str) -> str:
        safe_name = self._sanitize_filename(filename)
        target = self._upload_dir / safe_name
        if target.resolve() != (self._upload_dir / safe_name).resolve():
            raise ValueError("Invalid filename")
        with open(target, "wb") as f:
            shutil.copyfileobj(stream, f)
        return safe_name

    async def save_file_streaming(
        self,
        filename: str,
        async_chunk_iterator: AsyncIterator[bytes],
        max_bytes: int,
        sender_name: str,
    ) -> str:
        """Write chunks to disk under sender subfolder; raise FileSizeExceededError or QuotaExceededError."""
        safe_sender = self._sanitize_sender_name(sender_name)
        safe_name = self._sanitize_filename(filename)
        subdir = self._upload_dir / safe_sender
        subdir.mkdir(parents=True, exist_ok=True)
        target = subdir / safe_name
        try:
            target.resolve().relative_to(self._upload_dir.resolve())
        except ValueError:
            raise ValueError("Path outside upload directory")
        current_folder_size = self.get_folder_size_bytes(safe_sender)
        total = 0
        try:
            with open(target, "wb") as f:
                async for chunk in async_chunk_iterator:
                    total += len(chunk)
                    if total > max_bytes:
                        raise FileSizeExceededError()
                    if current_folder_size + total > self._user_quota_bytes:
                        raise QuotaExceededError()
                    f.write(chunk)
            return safe_name
        except FileSizeExceededError:
            target.unlink(missing_ok=True)
            raise
        except QuotaExceededError:
            target.unlink(missing_ok=True)
            raise

    def list_files(self) -> list[dict]:
        """List files in upload_dir (root files and per-sender subdirs); return {name, size, mtime, sender, path}."""
        result = []
        base = self._upload_dir.resolve()
        try:
            for p in self._upload_dir.iterdir():
                if p.is_file():
                    stat = p.stat()
                    result.append(
                        {
                            "name": p.name,
                            "size": stat.st_size,
                            "mtime": int(stat.st_mtime),
                            "sender": "",
                            "path": p.name,
                        }
                    )
                elif p.is_dir():
                    sender = p.name
                    try:
                        for f in p.iterdir():
                            if f.is_file():
                                stat = f.stat()
                                result.append(
                                    {
                                        "name": f.name,
                                        "size": stat.st_size,
                                        "mtime": int(stat.st_mtime),
                                        "sender": sender,
                                        "path": f"{sender}/{f.name}",
                                    }
                                )
                    except OSError:
                        pass
        except OSError:
            pass
        result.sort(key=lambda x: (x["mtime"], x["path"]), reverse=True)
        return result

    def list_files_in_folder(self, sender_name: str) -> list[dict]:
        """List files only in the sender's folder; return {name, size, mtime, path}. Returns [] if folder missing or invalid."""
        try:
            safe_sender = self._sanitize_sender_name(sender_name)
        except ValueError:
            return []
        subdir = self._upload_dir / safe_sender
        if not subdir.is_dir():
            return []
        result = []
        try:
            for f in subdir.iterdir():
                if f.is_file():
                    stat = f.stat()
                    result.append(
                        {
                            "name": f.name,
                            "size": stat.st_size,
                            "mtime": int(stat.st_mtime),
                            "path": f"{safe_sender}/{f.name}",
                        }
                    )
        except OSError:
            pass
        result.sort(key=lambda x: (x["mtime"], x["path"]), reverse=True)
        return result

    def get_file_path_in_folder(self, sender_name: str, filename: str) -> Path:
        """Return safe Path for a file in the sender's folder; only basename used for filename. Raise if invalid or not found."""
        safe_sender = self._sanitize_sender_name(sender_name)
        safe_name = self._sanitize_filename(Path(filename).name)
        return self.get_file_path(f"{safe_sender}/{safe_name}")

    def delete_folder(self, sender_name: str) -> None:
        """Remove the sender's folder and all its contents. No-op if sender_name invalid or not a dir."""
        try:
            safe_sender = self._sanitize_sender_name(sender_name)
        except ValueError:
            return
        folder = self._upload_dir / safe_sender
        if folder.is_dir():
            shutil.rmtree(folder)

    def delete_file(self, relative_path: str) -> None:
        """Delete a file by relative path (e.g. 'Alice/file.pdf'). Raise FileNotFoundError if not a file."""
        path = self._safe_join(relative_path)
        if not path.is_file():
            raise FileNotFoundError("Not a file or not found")
        path.unlink()

    def get_file_path(self, relative_path: str) -> Path:
        """Return safe Path for reading; raise if outside upload_dir."""
        path = self._safe_join(relative_path)
        if not path.is_file():
            raise FileNotFoundError("Not a file or not found")
        return path
