import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import ORMBase


class SubscriptionCreate(BaseModel):
    target_entity_id: uuid.UUID
    allocation_pct: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))


class SubscriptionRead(ORMBase):
    id: uuid.UUID
    user_id: uuid.UUID
    target_entity_id: uuid.UUID
    allocation_pct: Decimal
    is_active: bool
    started_at: datetime
    ended_at: datetime | None


class SubscriptionListResponse(BaseModel):
    model_config = ConfigDict()

    items: list[SubscriptionRead]
    total: int
