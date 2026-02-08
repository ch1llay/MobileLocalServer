import hashlib
import hmac
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from app.config import Settings


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def verify_pin(self, raw_pin: str) -> bool:
        if not self._settings.pin_hash or not self._settings.pin_salt:
            return False
        expected = self._hash_pin(raw_pin, self._settings.pin_salt)
        return hmac.compare_digest(expected, self._settings.pin_hash)

    @staticmethod
    def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
        if salt is None:
            salt = secrets.token_hex(16)
        h = AuthService._hash_pin(pin, salt)
        return h, salt

    @staticmethod
    def _hash_pin(pin: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256",
            pin.encode("utf-8"),
            salt.encode("utf-8"),
            iterations=100_000,
        ).hex()

    def create_session_token(self) -> str:
        now = int(time.time())
        expiry = now + self._settings.token_max_age_seconds
        payload = f"{now}:{expiry}"
        payload_b64 = urlsafe_b64encode(payload.encode()).decode().rstrip("=")
        sig = hmac.new(
            self._settings.secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"{payload_b64}.{sig}"

    def verify_token(self, token: str) -> bool:
        if not token:
            return False
        parts = token.split(".")
        if len(parts) != 2:
            return False
        payload_b64, sig = parts[0], parts[1]
        try:
            # restore padding for decode only
            pad = 4 - len(payload_b64) % 4
            if pad != 4:
                payload_b64_padded = payload_b64 + "=" * pad
            else:
                payload_b64_padded = payload_b64
            payload = urlsafe_b64decode(payload_b64_padded).decode()
        except Exception:
            return False
        expected_sig = hmac.new(
            self._settings.secret_key.encode(),
            payload_b64.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return False
        try:
            _, expiry_str = payload.split(":")
            expiry = int(expiry_str)
        except ValueError:
            return False
        return time.time() < expiry
