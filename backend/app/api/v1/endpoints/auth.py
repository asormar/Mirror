import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.enums import LedgerEntryType
from app.models.ledger import LedgerEntry
from app.models.user import User
from app.schemas.auth import LoginRequest, RefreshRequest, SignupRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_token_response(user_id: uuid.UUID) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
        expires_in=settings.jwt_access_token_expires_min * 60,
    )


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def signup(
    payload: SignupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    initial_capital = Decimal(str(settings.initial_virtual_capital))
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name,
        virtual_cash_balance=initial_capital,
        initial_capital=initial_capital,
    )
    db.add(user)
    await db.flush()

    db.add(
        LedgerEntry(
            user_id=user.id,
            entry_type=LedgerEntryType.INITIAL_DEPOSIT,
            amount_usd=initial_capital,
            cash_balance_after_usd=initial_capital,
            description="Initial virtual capital",
            created_at=datetime.now(UTC),
        )
    )

    try:
        await db.commit()
    except IntegrityError as err:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from err

    await db.refresh(user)
    return _build_token_response(user.id)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    user.last_login_at = datetime.now(UTC)
    await db.commit()
    return _build_token_response(user.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    try:
        token_payload = decode_token(payload.refresh_token, expected_type="refresh")
        sub = token_payload.get("sub")
        if not sub:
            raise ValueError("Missing sub claim")
        user_id = uuid.UUID(sub)
    except (ValueError, Exception) as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {err}",
        ) from err

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return _build_token_response(user.id)
