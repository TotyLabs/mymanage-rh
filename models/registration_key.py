"""
Registration Keys — Secure, token-based employer registration gating.
Keys are generated offline (or via admin), hashed with SHA-256, 
and verified via a two-step flow: verify key -> get temp JWT -> register.
"""
import sqlalchemy as sa
from sqlalchemy import (
    Column, Text, Boolean, Integer, String, CHAR,
    TIMESTAMP, ForeignKey, Index, func, text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from .base import Base


class RegistrationKey(Base):
    __tablename__ = "registration_keys"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    # SHA-256 hash of the raw key (the raw key is NEVER stored)
    key_hash = Column(CHAR(64), nullable=False, unique=True, index=True)

    # First 8 chars of the raw key for admin debugging (e.g., "YCP-ab12")
    key_prefix = Column(String(12), nullable=False)

    # Type of registration this key allows
    key_type = Column(String(20), nullable=False, server_default=text("'employer'"))

    # State
    is_active = Column(Boolean, nullable=False, server_default=sa.text("true"))
    is_revoked = Column(Boolean, nullable=False, server_default=sa.text("false"))

    # Usage limits
    max_uses = Column(Integer, nullable=False, server_default=text("1"))
    current_uses = Column(Integer, nullable=False, server_default=text("0"))

    # Expiration
    expires_at = Column(TIMESTAMP(timezone=True))

    # Metadata
    label = Column(Text)  # Optional admin-friendly description
    created_by = Column(PG_UUID(as_uuid=False))  # Admin who generated the key
    used_by_org_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    used_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("idx_regkeys_active", "is_active", "is_revoked"),
    )
