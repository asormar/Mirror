import uuid

import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    h = hash_password("hunter2-correct-horse")
    assert h != "hunter2-correct-horse"
    assert verify_password("hunter2-correct-horse", h)
    assert not verify_password("hunter3-wrong-horse", h)


def test_password_hash_is_salted() -> None:
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2
    assert verify_password("same-password", h1)
    assert verify_password("same-password", h2)


def test_jwt_round_trip_access_and_refresh() -> None:
    user_id = uuid.uuid4()
    access = create_access_token(user_id)
    refresh = create_refresh_token(user_id)

    access_payload = decode_token(access, expected_type="access")
    assert access_payload["sub"] == str(user_id)
    assert access_payload["type"] == "access"

    refresh_payload = decode_token(refresh, expected_type="refresh")
    assert refresh_payload["sub"] == str(user_id)
    assert refresh_payload["type"] == "refresh"


def test_jwt_wrong_type_rejected() -> None:
    user_id = uuid.uuid4()
    refresh = create_refresh_token(user_id)
    with pytest.raises(ValueError, match="Expected token type"):
        decode_token(refresh, expected_type="access")


def test_jwt_garbage_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid token"):
        decode_token("not.a.valid.jwt", expected_type="access")
