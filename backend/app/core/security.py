import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def _encode_token(subject: uuid.UUID | str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(UTC)
    expire = now + expires_delta
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": str(uuid.uuid4()),
        "type": token_type,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(subject: uuid.UUID | str) -> str:
    return _encode_token(
        subject,
        "access",
        timedelta(minutes=settings.jwt_access_token_expires_min),
    )


def create_refresh_token(subject: uuid.UUID | str) -> str:
    return _encode_token(
        subject,
        "refresh",
        timedelta(days=settings.jwt_refresh_token_expires_days),
    )


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        raise ValueError(f"Invalid token: {e}") from e

    actual_type = payload.get("type")
    if actual_type != expected_type:
        raise ValueError(f"Expected token type '{expected_type}', got '{actual_type}'")

    return payload
