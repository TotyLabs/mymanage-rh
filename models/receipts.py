import sqlalchemy as sa
from sqlalchemy import (
    Column,
    Text,
    Boolean,
    TIMESTAMP,
    String,
    ForeignKey,
    DateTime,
    func,
    LargeBinary
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from .base import Base

class Receipt(Base):
    __tablename__ = "receipts"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()"))

    user_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    company_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    file_path = Column(Text, nullable=False)
    file_hash = Column(String(64), nullable=False) # SHA256
    receipt_metadata = Column(sa.JSON, server_default=sa.text("'{}'"), nullable=False)

    status = Column(String(50), nullable=False, server_default=sa.text("'pending'")) # pending | signed
    
    signed_at = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, nullable=False, server_default=sa.text("false"))

    # Signatures
    employer_signed_at = Column(TIMESTAMP(timezone=True))
    employee_signed_at = Column(TIMESTAMP(timezone=True))

    # Flags
    is_signed = Column(Boolean, nullable=False, server_default=sa.text("false"))
    document_locked = Column(Boolean, nullable=False, server_default=sa.text("false"))
    processing_signature = Column(Boolean, nullable=False, server_default=sa.text("false"))
    
    # Requirements
    requires_employer = Column(Boolean, nullable=False, server_default=sa.text("true"))
    requires_employee = Column(Boolean, nullable=False, server_default=sa.text("true"))

    # Identifiers
    verification_id = Column(Text, unique=True, index=True)
    batch_id = Column(PG_UUID(as_uuid=False), ForeignKey("payroll_batches.id", ondelete="SET NULL"))

    # Legal Snapshot Bundle (Enterprise Non-Repudiation)
    signature_snapshot = Column(LargeBinary) # Snapshot of signature used
    signature_hash = Column(String(64)) # SHA256 of the snapshot
    tsa_timestamp = Column(TIMESTAMP(timezone=True))

    # Employee Identity Snapshot (immutable after creation)
    snapshot_employee_name = Column(Text)
    snapshot_employee_dni  = Column(Text)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    organization = relationship("Organization", foreign_keys=[company_id])

    __table_args__ = (
        sa.Index("idx_receipts_user_status", "user_id", "status"),
    )
