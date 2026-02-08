import re
import shutil
from pathlib import Path
from typing import BinaryIO


# Unsafe characters for filenames; keep alphanumeric, dots, hyphens, underscores
UNSAFE_FILENAME_RE = re.compile(r"[^\w.\- ]", re.UNICODE)


class UploadService:
    def __init__(self, upload_dir: Path) -> None:
        self._upload_dir = upload_dir.resolve()

    def _safe_join(self, relative_path: str) -> Path:
        """Resolve relative_path against upload_dir; raise if outside upload_dir."""
        base = self._upload_dir
        # Normalize: no leading slash, no ".."
        path_str = relative_path.lstrip("/\\")
        parts = Path(path_str).parts
        if any(p == ".." for p in parts):
            raise ValueError("Path traversal not allowed")
        resolved = (base / Path(*parts)).resolve()
        if not str(resolved).startswith(str(base)):
            raise ValueError("Path outside upload directory")
        return resolved

    def _sanitize_filename(self, filename: str) -> str:
        """Return a safe basename (no path, no unsafe chars)."""
        name = Path(filename).name
        name = UNSAFE_FILENAME_RE.sub("_", name)
        if not name.strip():
            name = "unnamed"
        return name

    def save_file(self, stream: BinaryIO, filename: str) -> str:
        safe_name = self._sanitize_filename(filename)
        target = self._upload_dir / safe_name
        if target.resolve() != (self._upload_dir / safe_name).resolve():
            raise ValueError("Invalid filename")
        with open(target, "wb") as f:
            shutil.copyfileobj(stream, f)
        return safe_name

    def list_files(self) -> list[dict]:
        """List files in upload_dir; return list of {name, size, mtime}."""
        result = []
        try:
            for p in self._upload_dir.iterdir():
                if p.is_file():
                    stat = p.stat()
                    result.append(
                        {
                            "name": p.name,
                            "size": stat.st_size,
                            "mtime": int(stat.st_mtime),
                        }
                    )
        except OSError:
            pass
        result.sort(key=lambda x: (x["mtime"], x["name"]), reverse=True)
        return result

    def get_file_path(self, relative_path: str) -> Path:
        """Return safe Path for reading; raise if outside upload_dir."""
        path = self._safe_join(relative_path)
        if not path.is_file():
            raise FileNotFoundError("Not a file or not found")
        return path
