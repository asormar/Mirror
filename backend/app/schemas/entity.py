import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import EntityType
from app.schemas.common import ORMBase


class TargetEntityRead(ORMBase):
    id: uuid.UUID
    slug: str
    name: str
    entity_type: EntityType
    external_id: str
    jurisdiction: str
    is_active: bool
    created_at: datetime


class TargetEntityListResponse(BaseModel):
    items: list[TargetEntityRead]
    total: int
    page: int
    page_size: int
