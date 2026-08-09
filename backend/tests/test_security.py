import jwt
import pytest

from education_platform.modules.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("secret-pass")
    assert verify_password(hashed, "secret-pass")
    assert not verify_password(hashed, "other")


def test_access_token_roundtrip() -> None:
    from uuid import uuid4

    user_id = uuid4()
    institution_id = uuid4()
    token = create_access_token(user_id=user_id, institution_id=institution_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "access"


def test_refresh_token_includes_hash() -> None:
    from uuid import uuid4

    token, token_hash, expires_at = create_refresh_token(user_id=uuid4())
    payload = decode_token(token)
    assert payload["type"] == "refresh"
    assert payload["jti"] == token_hash
    assert expires_at.tzinfo is not None


def test_decode_invalid_token() -> None:
    with pytest.raises(jwt.PyJWTError):
        decode_token("not-a-jwt")
