"""End-to-end tests for the auth + /me flow against a real PostgreSQL."""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LedgerEntryType
from app.models.ledger import LedgerEntry
from app.models.user import User
from tests.integration.conftest import _signup

pytestmark = pytest.mark.integration


async def test_signup_creates_user_with_initial_capital(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, access, _refresh = await _signup(client)

    assert access
    assert user.email == "alice@example.com"
    assert user.full_name == "Alice"
    assert user.virtual_cash_balance == Decimal("100000.00")
    assert user.initial_capital == Decimal("100000.00")
    assert user.is_active is True
    assert user.last_login_at is None


async def test_signup_writes_initial_deposit_ledger_entry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _user, _access, _refresh = await _signup(client, email="bob@example.com")

    result = await db_session.execute(select(LedgerEntry).order_by(LedgerEntry.created_at))
    entries = result.scalars().all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.entry_type == LedgerEntryType.INITIAL_DEPOSIT
    assert entry.amount_usd == Decimal("100000.00")
    assert entry.cash_balance_after_usd == Decimal("100000.00")
    assert entry.virtual_trade_id is None
    assert entry.description == "Initial virtual capital"


async def test_ledger_cash_balance_after_matches_user_balance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    user, _access, _refresh = await _signup(client, email="carol@example.com")

    sum_after = await db_session.execute(
        select(func.coalesce(func.sum(LedgerEntry.amount_usd), 0)).where(
            LedgerEntry.user_id == user.id
        )
    )
    total = sum_after.scalar_one()
    assert Decimal(str(total)) == user.virtual_cash_balance


async def test_duplicate_signup_returns_409(client: AsyncClient) -> None:
    await _signup(client, email="dupe@example.com")
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": "dupe@example.com", "password": "Secret123!", "full_name": "Dupe"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


async def test_signup_with_weak_password_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": "weak@example.com", "password": "short", "full_name": "Weak"},
    )
    assert response.status_code == 422


async def test_login_returns_tokens_and_updates_last_login(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _signup(client, email="login@example.com")

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "Secret123!"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]

    result = await db_session.execute(select(User).where(User.email == "login@example.com"))
    user = result.scalar_one()
    assert user.last_login_at is not None


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await _signup(client, email="wrong@example.com")
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "NOPE1234!"},
    )
    assert response.status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Secret123!"},
    )
    assert response.status_code == 401


async def test_refresh_exchanges_refresh_for_new_tokens(client: AsyncClient) -> None:
    _user, first_access, refresh = await _signup(client, email="refresh@example.com")
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != first_access


async def test_refresh_with_access_token_rejected(client: AsyncClient) -> None:
    _user, access, _refresh = await _signup(client, email="mismatch@example.com")
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access},
    )
    assert response.status_code == 401


async def test_me_returns_current_user_profile(client: AsyncClient) -> None:
    user, access, _refresh = await _signup(client, email="me@example.com", full_name="Me User")
    response = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "me@example.com"
    assert body["full_name"] == "Me User"
    assert body["is_active"] is True
    assert Decimal(body["virtual_cash_balance"]) == user.virtual_cash_balance


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_patch_me_updates_full_name(client: AsyncClient) -> None:
    _user, access, _refresh = await _signup(client, email="patch@example.com", full_name="Old")
    response = await client.patch(
        "/api/v1/me",
        json={"full_name": "New"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "New"


async def test_disabled_user_cannot_login(client: AsyncClient, db_session: AsyncSession) -> None:
    _user, _access, _refresh = await _signup(client, email="disabled@example.com")

    from sqlalchemy import select

    result = await db_session.execute(select(User).where(User.email == "disabled@example.com"))
    db_user = result.scalar_one()
    db_user.is_active = False
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "disabled@example.com", "password": "Secret123!"},
    )
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()
