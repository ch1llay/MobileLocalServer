import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path


def _hash_code(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class UploadCodesService:
    def __init__(self, codes_file: Path) -> None:
        self._path = codes_file.resolve()

    def _load(self) -> list[dict]:
        if not self._path.exists():
            return []
        data = self._path.read_text(encoding="utf-8")
        return json.loads(data) if data.strip() else []

    def _save(self, records: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def create_code(self, name: str) -> tuple[str, str, str]:
        """Generate a new 6-digit PIN, store its hash and name, return (pin, code_hash, created_at_iso)."""
        name = name.strip()
        if not name:
            raise ValueError("Name is required")
        pin = "".join(secrets.choice("0123456789") for _ in range(6))
        code_hash = _hash_code(pin)
        created_at = datetime.now(UTC).isoformat()
        records = self._load()
        records.append({"code_hash": code_hash, "label": name, "created_at": created_at})
        self._save(records)
        return pin, code_hash, created_at

    def get_name_by_code(self, raw_code: str) -> str | None:
        """Hash input, find record by code_hash, return label (user name). Return None if not found or label empty."""
        if not raw_code or not raw_code.strip():
            return None
        h = _hash_code(raw_code.strip())
        records = self._load()
        for r in records:
            if r.get("code_hash") == h:
                label = r.get("label", "") or ""
                return label.strip() or None
        return None

    def verify_code(self, raw_code: str) -> bool:
        """Return True if the code is in the stored list (by hash)."""
        if not raw_code or not raw_code.strip():
            return False
        h = _hash_code(raw_code.strip())
        records = self._load()
        return any(r.get("code_hash") == h for r in records)

    def list_users(self) -> list[dict]:
        """Return list of {label, created_at} without code_hash."""
        records = self._load()
        return [{"label": r.get("label", ""), "created_at": r.get("created_at", "")} for r in records]

    def delete_user_by_index(self, index: int) -> str | None:
        """Remove user at index; save; return label of removed user or None if index invalid."""
        records = self._load()
        if index < 0 or index >= len(records):
            return None
        record = records.pop(index)
        label = (record.get("label") or "").strip()
        self._save(records)
        return label or None
