"""Integration test fixtures: real PostgreSQL via Docker.

The autouse `_db_available` fixture will skip every test in this directory
if PostgreSQL cannot be reached on localhost:5432. This means the suite is
safe to collect even when Docker is down.
"""

# ruff: noqa: E402  env-var setup must run before app imports

from __future__ import annotations

import os
import socket
import sys
from collections.abc import AsyncGenerator
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://copytrade_user:copytrade_password@localhost:5433/mirror_test",
)

import pytest
import pytest_asyncio
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from alembic import command as alembic_command
from app import models as _models  # noqa: F401  register all model classes
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.enums import EntityType
from app.models.target_entity import TargetEntity
from app.models.user import User

TEST_DB_URL = os.environ["DATABASE_URL"]
ADMIN_DB_URL = TEST_DB_URL.replace("/mirror_test", "/postgres")


def _postgres_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 5433), timeout=1.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _db_available() -> AsyncGenerator[None, None]:
    if not _postgres_reachable():
        pytest.skip(
            "PostgreSQL not reachable on localhost:5432 (is `docker compose up -d db` running?)"
        )

    admin_engine = create_async_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'mirror_test'")
            )
            if not result.scalar():
                await conn.execute(text("CREATE DATABASE mirror_test"))
    finally:
        await admin_engine.dispose()

    cfg = AlembicConfig(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB_URL)
    alembic_command.upgrade(cfg, "head")

    yield


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncGenerator[None, None]:
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE ledger_entries, positions, virtual_trades, holdings, "
                "portfolio_snapshots, publication_events, subscriptions, target_entities, "
                "daily_pnl_snapshots, users RESTART IDENTITY CASCADE"
            )
        )
        await session.commit()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def target_entity(db_session: AsyncSession) -> TargetEntity:
    entity = TargetEntity(
        slug="berkshire-hathaway",
        name="Berkshire Hathaway",
        entity_type=EntityType.HEDGE_FUND,
        external_id="0001067983",
        jurisdiction="US",
        is_active=True,
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def second_target_entity(db_session: AsyncSession) -> TargetEntity:
    entity = TargetEntity(
        slug="bridgewater-associates",
        name="Bridgewater Associates",
        entity_type=EntityType.HEDGE_FUND,
        external_id="0001350694",
        jurisdiction="US",
        is_active=True,
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


@pytest_asyncio.fixture
async def inactive_target_entity(db_session: AsyncSession) -> TargetEntity:
    entity = TargetEntity(
        slug="deprecated-fund",
        name="Deprecated Fund",
        entity_type=EntityType.HEDGE_FUND,
        external_id="0009999999",
        jurisdiction="US",
        is_active=False,
    )
    db_session.add(entity)
    await db_session.commit()
    await db_session.refresh(entity)
    return entity


async def _signup(
    client: AsyncClient,
    email: str = "alice@example.com",
    password: str = "Secret123!",
    full_name: str = "Alice",
) -> tuple[User, str, str]:
    response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    user = await _load_user_by_email(email)
    return user, body["access_token"], body["refresh_token"]


async def _load_user_by_email(email: str) -> User:
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()


@pytest_asyncio.fixture
async def signed_up_user(
    client: AsyncClient,
) -> AsyncGenerator[tuple[User, str, str], None]:
    yield await _signup(client)
