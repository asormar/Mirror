"""End-to-end tests for the subscriptions rules against a real PostgreSQL."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import Subscription
from app.models.target_entity import TargetEntity
from tests.integration.conftest import _signup

pytestmark = pytest.mark.integration


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _subscribe(
    client: AsyncClient,
    token: str,
    target_entity_id: str,
    allocation_pct: str | Decimal,
) -> tuple[int, dict[str, Any]]:
    response = await client.post(
        "/api/v1/subscriptions",
        json={
            "target_entity_id": target_entity_id,
            "allocation_pct": str(allocation_pct),
        },
        headers=_auth_headers(token),
    )
    return response.status_code, response.json() if response.content else {}


async def test_list_subscriptions_empty_by_default(
    client: AsyncClient, target_entity: TargetEntity
) -> None:
    _user, access, _refresh = await _signup(client, email="empty@example.com")
    response = await client.get("/api/v1/subscriptions", headers=_auth_headers(access))
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_create_subscription_within_limit(
    client: AsyncClient, target_entity: TargetEntity
) -> None:
    _user, access, _refresh = await _signup(client, email="ok@example.com")
    status, body = await _subscribe(client, access, str(target_entity.id), "50")
    assert status == 201
    assert Decimal(body["allocation_pct"]) == Decimal("50.00")
    assert body["is_active"] is True
    assert body["ended_at"] is None


async def test_two_subscriptions_totaling_100_succeed(
    client: AsyncClient,
    target_entity: TargetEntity,
    second_target_entity: TargetEntity,
) -> None:
    _user, access, _refresh = await _signup(client, email="hundred@example.com")
    s1, _ = await _subscribe(client, access, str(target_entity.id), "60")
    s2, _ = await _subscribe(client, access, str(second_target_entity.id), "40")
    assert s1 == 201
    assert s2 == 201


async def test_subscription_exceeding_100_returns_400(
    client: AsyncClient,
    target_entity: TargetEntity,
    second_target_entity: TargetEntity,
) -> None:
    _user, access, _refresh = await _signup(client, email="over@example.com")
    s1, _ = await _subscribe(client, access, str(target_entity.id), "60")
    s2, body = await _subscribe(client, access, str(second_target_entity.id), "50")
    assert s1 == 201
    assert s2 == 400
    assert "100%" in body["detail"]


async def test_duplicate_active_subscription_returns_409(
    client: AsyncClient, target_entity: TargetEntity
) -> None:
    _user, access, _refresh = await _signup(client, email="dupe@example.com")
    s1, _ = await _subscribe(client, access, str(target_entity.id), "30")
    s2, body = await _subscribe(client, access, str(target_entity.id), "40")
    assert s1 == 201
    assert s2 == 409
    assert body["detail"] == "Already subscribed to this target entity"


async def test_inactive_target_returns_404(
    client: AsyncClient, inactive_target_entity: TargetEntity
) -> None:
    _user, access, _refresh = await _signup(client, email="ghost@example.com")
    status, body = await _subscribe(client, access, str(inactive_target_entity.id), "10")
    assert status == 404
    assert "inactive" in body["detail"]


async def test_unknown_target_returns_404(client: AsyncClient) -> None:
    _user, access, _refresh = await _signup(client, email="404@example.com")
    status, _body = await _subscribe(client, access, str(uuid.uuid4()), "10")
    assert status == 404


async def test_soft_delete_then_resubscribe_same_target(
    client: AsyncClient,
    target_entity: TargetEntity,
    db_session: AsyncSession,
) -> None:
    _user, access, _refresh = await _signup(client, email="cycle@example.com")
    s1, first_body = await _subscribe(client, access, str(target_entity.id), "30")
    assert s1 == 201
    first_id = first_body["id"]

    response = await client.delete(
        f"/api/v1/subscriptions/{first_id}", headers=_auth_headers(access)
    )
    assert response.status_code == 204

    result = await db_session.execute(select(Subscription).where(Subscription.id == first_id))
    sub = result.scalar_one()
    assert sub.is_active is False
    assert sub.ended_at is not None

    s2, second_body = await _subscribe(client, access, str(target_entity.id), "40")
    assert s2 == 201
    assert second_body["id"] != first_id
    assert Decimal(second_body["allocation_pct"]) == Decimal("40.00")


async def test_soft_delete_frees_allocation_budget(
    client: AsyncClient,
    target_entity: TargetEntity,
    second_target_entity: TargetEntity,
) -> None:
    _user, access, _refresh = await _signup(client, email="budget@example.com")
    s1, first_body = await _subscribe(client, access, str(target_entity.id), "60")
    assert s1 == 201
    first_id = first_body["id"]

    over, _ = await _subscribe(client, access, str(second_target_entity.id), "50")
    assert over == 400

    response = await client.delete(
        f"/api/v1/subscriptions/{first_id}", headers=_auth_headers(access)
    )
    assert response.status_code == 204

    retry, _ = await _subscribe(client, access, str(second_target_entity.id), "50")
    assert retry == 201


async def test_delete_unknown_subscription_returns_404(client: AsyncClient) -> None:
    _user, access, _refresh = await _signup(client, email="del404@example.com")
    response = await client.delete(
        f"/api/v1/subscriptions/{uuid.uuid4()}", headers=_auth_headers(access)
    )
    assert response.status_code == 404


async def test_delete_other_users_subscription_returns_404(
    client: AsyncClient, target_entity: TargetEntity
) -> None:
    _alice, alice_access, _ = await _signup(client, email="alice@example.com")
    status, body = await _subscribe(client, alice_access, str(target_entity.id), "20")
    assert status == 201
    sub_id = body["id"]

    _bob, bob_access, _ = await _signup(client, email="bob@example.com")
    response = await client.delete(
        f"/api/v1/subscriptions/{sub_id}", headers=_auth_headers(bob_access)
    )
    assert response.status_code == 404


async def test_subscriptions_are_isolated_per_user(
    client: AsyncClient, target_entity: TargetEntity
) -> None:
    _alice, alice_access, _ = await _signup(client, email="iso-alice@example.com")
    _bob, bob_access, _ = await _signup(client, email="iso-bob@example.com")

    s1, _ = await _subscribe(client, alice_access, str(target_entity.id), "80")
    s2, _ = await _subscribe(client, bob_access, str(target_entity.id), "70")
    assert s1 == 201
    assert s2 == 201

    alice_list = await client.get("/api/v1/subscriptions", headers=_auth_headers(alice_access))
    bob_list = await client.get("/api/v1/subscriptions", headers=_auth_headers(bob_access))
    assert alice_list.json()["total"] == 1
    assert bob_list.json()["total"] == 1
    assert alice_list.json()["items"][0]["user_id"] != bob_list.json()["items"][0]["user_id"]


async def test_list_entities_returns_active_only_by_default(
    client: AsyncClient,
    target_entity: TargetEntity,
    inactive_target_entity: TargetEntity,
) -> None:
    response = await client.get("/api/v1/entities")
    assert response.status_code == 200
    body = response.json()
    slugs = {item["slug"] for item in body["items"]}
    assert "berkshire-hathaway" in slugs
    assert "deprecated-fund" not in slugs


async def test_list_entities_includes_inactive_when_requested(
    client: AsyncClient,
    target_entity: TargetEntity,
    inactive_target_entity: TargetEntity,
) -> None:
    response = await client.get("/api/v1/entities?active_only=false")
    assert response.status_code == 200
    body = response.json()
    slugs = {item["slug"] for item in body["items"]}
    assert "berkshire-hathaway" in slugs
    assert "deprecated-fund" in slugs


async def test_get_entity_by_id(client: AsyncClient, target_entity: TargetEntity) -> None:
    response = await client.get(f"/api/v1/entities/{target_entity.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "berkshire-hathaway"
    assert body["entity_type"] == "HEDGE_FUND"
