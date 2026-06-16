import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.target_entity import TargetEntity
from app.schemas.entity import TargetEntityListResponse, TargetEntityRead

router = APIRouter(prefix="/entities", tags=["entities"])


@router.get("", response_model=TargetEntityListResponse)
async def list_entities(
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    entity_type: str | None = Query(None),
    active_only: bool = Query(True),
) -> TargetEntityListResponse:
    base = select(TargetEntity)
    count_stmt = select(func.count()).select_from(TargetEntity)

    if active_only:
        base = base.where(TargetEntity.is_active.is_(True))
        count_stmt = count_stmt.where(TargetEntity.is_active.is_(True))
    if entity_type is not None:
        base = base.where(TargetEntity.entity_type == entity_type)
        count_stmt = count_stmt.where(TargetEntity.entity_type == entity_type)

    total = (await db.execute(count_stmt)).scalar_one()
    rows = (
        (
            await db.execute(
                base.order_by(TargetEntity.name).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )

    return TargetEntityListResponse(
        items=[TargetEntityRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{entity_id}", response_model=TargetEntityRead)
async def get_entity(
    entity_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TargetEntity:
    entity = await db.get(TargetEntity, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target entity not found",
        )
    return entity
