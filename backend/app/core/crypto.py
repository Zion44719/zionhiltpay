"""
Encryption + fingerprinting for government ID numbers.

- encrypt_id / decrypt_id : Fernet (AES-128-CBC + HMAC) so the number can be recovered for manual
  KYC review, but a database dump alone reveals nothing.
- id_fingerprint          : keyed HMAC-SHA256 of the normalised number. Lets us enforce "one ID,
  one account" without being able to read or even brute-force-guess the number from the DB.
Never log either the plaintext or the ciphertext.
"""
import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet_key() -> bytes:
    if settings.DATA_ENCRYPTION_KEY:
        return settings.DATA_ENCRYPTION_KEY.encode()
    # development fallback only; production startup refuses to run without an explicit key
    return base64.urlsafe_b64encode(hashlib.sha256(b"zhp-data-key:" + settings.JWT_SECRET_KEY.encode()).digest())


def validate_encryption_key() -> None:
    """Raises ValueError if the configured key is malformed (called at startup)."""
    try:
        Fernet(_fernet_key())
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "DATA_ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc


def encrypt_id(plaintext: str) -> str:
    return Fernet(_fernet_key()).encrypt(plaintext.encode()).decode()


def decrypt_id(token: str) -> str:
    try:
        return Fernet(_fernet_key()).decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Stored ID could not be decrypted - the encryption key has changed") from exc


def id_fingerprint(id_type: str, normalized_number: str) -> str:
    key = hashlib.sha256(b"zhp-id-fingerprint:" + _fernet_key()).digest()
    return hmac.new(key, f"{id_type}:{normalized_number}".encode(), hashlib.sha256).hexdigest()
