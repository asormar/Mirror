import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.subscription import Subscription
from app.models.target_entity import TargetEntity
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionCreate,
    SubscriptionListResponse,
    SubscriptionRead,
)

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=SubscriptionListResponse)
async def list_subscriptions(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SubscriptionListResponse:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == current_user.id)
        .order_by(Subscription.started_at.desc())
    )
    rows = result.scalars().all()
    return SubscriptionListResponse(
        items=[SubscriptionRead.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.post(
    "",
    response_model=SubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    payload: SubscriptionCreate,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Subscription:
    entity = await db.get(TargetEntity, payload.target_entity_id)
    if entity is None or not entity.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target entity not found or inactive",
        )

    existing = await db.execute(
        select(Subscription).where(
            Subscription.user_id == current_user.id,
            Subscription.target_entity_id == payload.target_entity_id,
            Subscription.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already subscribed to this target entity",
        )

    sum_result = await db.execute(
        select(func.coalesce(func.sum(Subscription.allocation_pct), 0)).where(
            Subscription.user_id == current_user.id,
            Subscription.is_active.is_(True),
        )
    )
    current_sum = sum_result.scalar_one() or Decimal("0")
    if Decimal(str(current_sum)) + payload.allocation_pct > Decimal("100"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Total allocation across subscriptions would exceed 100%",
        )

    sub = Subscription(
        user_id=current_user.id,
        target_entity_id=payload.target_entity_id,
        allocation_pct=payload.allocation_pct,
        started_at=datetime.now(UTC),
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.delete("/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription(
    subscription_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.user_id == current_user.id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription not found",
        )
    if not sub.is_active:
        return

    sub.is_active = False
    sub.ended_at = datetime.now(UTC)
    await db.commit()
