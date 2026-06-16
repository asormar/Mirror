import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMBase


class UserRead(ORMBase):
    id: uuid.UUID
    email: str
    full_name: str | None
    virtual_cash_balance: Decimal
    initial_capital: Decimal
    is_active: bool
    is_verified: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
