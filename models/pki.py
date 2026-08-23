import sqlalchemy as sa
from sqlalchemy import (
    Column,
    Text,
    Integer,
    DateTime,
    func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from .base import Base

class KeyMetadata(Base):
    """
    Tracks PKI key versions, fingerprints, and state for Soft-HSM rotation support.
    """
    __tablename__ = "pki_key_metadata"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=sa.text("uuid_generate_v4()"))
    
    key_id = Column(Text, nullable=False, index=True) # e.g. 'root_ca', 'intermediate'
    version = Column(Integer, nullable=False, server_default=sa.text("1"))
    
    fingerprint = Column(Text, nullable=False, unique=True)
    encrypted_path = Column(Text, nullable=False) # Path to the .enc file
    
    status = Column(Text, nullable=False, server_default=sa.text("'active'")) # active | retired | revoked
    
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    retired_at = Column(DateTime(timezone=True))

    __table_args__ = (
        sa.UniqueConstraint("key_id", "version", name="uq_pki_key_id_version"),
    )
