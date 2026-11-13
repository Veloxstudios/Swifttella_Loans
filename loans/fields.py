"""Model field that encrypts its value at rest with Fernet (AES-128 + HMAC)."""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


class EncryptedCharField(models.TextField):
    """Stores ciphertext in the database; Python code sees plain text.

    Encrypted values cannot be searched or filtered in SQL, so keep a
    separate non-sensitive column (such as the last four digits) for lookups.
    """

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, ""):
            return value
        return _fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return _fernet().decrypt(value.encode()).decode()
        except InvalidToken as exc:  # wrong key or tampered data
            raise ValueError("Could not decrypt a protected field; check FIELD_ENCRYPTION_KEY.") from exc

    def to_python(self, value):
        return value
