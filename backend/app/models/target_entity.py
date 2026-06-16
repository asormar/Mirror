from typing import Any

from sqlalchemy import Boolean, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPKMixin
from app.models.enums import EntityType


class TargetEntity(Base, UUIDPKMixin, TimestampMixin):
    __tablename__ = "target_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "external_id", name="uq_entity_type_external_id"),
        Index("ix_target_entities_active", "is_active", "entity_type"),
    )

    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_type: Mapped[EntityType] = mapped_column(nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(8), nullable=False, default="US")

    extra_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    subscriptions = relationship("Subscription", back_populates="target_entity")
    publications = relationship("PublicationEvent", back_populates="target_entity")
