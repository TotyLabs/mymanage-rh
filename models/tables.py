import uuid
import sqlalchemy as sa
from sqlalchemy import (
    Column,
    Text,
    Boolean,
    Integer,
    BigInteger,
    CHAR,
    TIMESTAMP,
    DATE,
    DateTime,
    String,
    ForeignKey,
    UniqueConstraint,
    Index,
    CheckConstraint,
    func,
    text,
    Numeric
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy import Enum as SAEnum

from .base import Base
from .enums import ReceiptStatus, SignatureStatus, ActorType, UserRole, EmployeeStatus, UserStatus


# =====================================================
# USERS
# =====================================================
class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    email = Column(Text, nullable=False)
    password_hash = Column(Text, nullable=False)

    role = Column(
        SAEnum(UserRole, name="user_role", create_type=False),
        nullable=False,
        server_default=text("'employee'")
    )

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    employee_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("employees.id", ondelete="SET NULL"),
        unique=True,
    )

    full_name = Column(Text, nullable=False)

    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    email_verified = Column(Boolean, nullable=False, server_default=text("false"))
    key_management_mode = Column(String(20), server_default=text("'user_managed'"))

    # GAP-OTP: Identity verification state
    user_status = Column(
        SAEnum(UserStatus, name="user_status", create_type=False),
        nullable=False,
        server_default=text("'full'")
    )
    is_verified = Column(Boolean, nullable=False, server_default=text("false"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_login = Column(TIMESTAMP(timezone=True))
    
    # TOS Acceptance (Audit-ready)
    tos_accepted = Column(Boolean, nullable=False, server_default=text("false"))
    tos_accepted_at = Column(TIMESTAMP(timezone=True))
    tos_version = Column(String(20))
    tos_accept_ip = Column(INET)

    is_deleted = Column(Boolean, nullable=False, server_default=sa.text("false"))
    deleted_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint("email", "organization_id", name="uq_user_email_org"),
    )


# =====================================================
# IDENTITY VERIFICATION (OTP)
# =====================================================
class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    
    user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    receipt_id = Column(PG_UUID(as_uuid=False), ForeignKey("payroll_receipts.id", ondelete="CASCADE"), index=True)
    
    signature_token = Column(Text) # Tied to a specific signing session
    code_hash = Column(CHAR(64), nullable=False)
    
    # context_hash = hash(receipt_id + signature_token + code) for strong binding
    context_hash = Column(Text, index=True)
    
    channel = Column(String(20), server_default=text("'email'"))
    
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    attempts = Column(Integer, server_default=text("0"))
    
    verified = Column(Boolean, server_default=text("false"))
    verified_at = Column(TIMESTAMP(timezone=True))
    used_at = Column(TIMESTAMP(timezone=True)) # Replay protection
    
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    ip_address = Column(INET)


# =====================================================
# USER SESSIONS
# =====================================================
class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    session_token_hash = Column(CHAR(64), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)

    ip_address = Column(INET)
    user_agent = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

# =====================================================
# PASSWORD RESET TOKENS
# =====================================================
class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    token_hash = Column(CHAR(64), nullable=False, unique=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    used_at = Column(TIMESTAMP(timezone=True))  # NULL = unused; NOT NULL = consumed (single-use)

    ip_address = Column(INET)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_prt_user", "user_id"),
        Index("idx_prt_expires", "expires_at"),
    )


# =====================================================
# USER SIGNATURES
# =====================================================
class UserSignature(Base):
    __tablename__ = "user_signatures"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    signature_path = Column(Text, nullable=False)
    signature_hash = Column(Text)
    
    version = Column(Integer, nullable=False, server_default=text("1"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

# =====================================================
# ORGANIZATIONS
# =====================================================
class Organization(Base):
    __tablename__ = "organizations"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    name = Column(Text, nullable=False)
    slug = Column(Text, nullable=False, unique=True)

    # Internal normalized name for case-insensitive matching
    normalized_name = Column(Text)

    is_active = Column(Boolean, nullable=False, server_default=text("true"))
    logo_path = Column(Text)
    cuit = Column(Text)
    email = Column(Text)  # Organization contact email (used for Reply-To in signature emails)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("name", name="uq_organization_name"),
        UniqueConstraint("cuit", name="uq_organization_cuit"),
    )


# =====================================================
# EMPLOYEES
# =====================================================
class Employee(Base):
    __tablename__ = "employees"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    first_name = Column(Text, nullable=False)
    last_name = Column(Text)
    
    # Legajo / File Number (Unique per organization)
    file_number = Column(Text)

    # Identidad legal
    dni = Column(Text, nullable=False)
    cuil = Column(Text)
    
    document_type = Column(Text, server_default=text("'DNI'"))
    document_number = Column(Text)

    email = Column(Text)
    phone = Column(Text)

    status = Column(
        SAEnum(EmployeeStatus, name="employee_status", create_type=False),
        nullable=False,
        server_default=text("'pre_registered'")
    )
    status_reason = Column(Text)

    profile_completed = Column(Boolean, nullable=False, server_default=text("false"))
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    # Datos personales
    gender = Column(Text)
    birth_date = Column(DATE)
    marital_status = Column(Text)
    nationality = Column(Text)
    
    # Domicilio
    address = Column(Text)
    address_number = Column(Text)
    city = Column(Text)
    province = Column(Text)
    postal_code = Column(Text)

    # Datos documentales / Afiliaciones
    health_insurance = Column(Text)
    health_insurance_number = Column(Text)
    union = Column(Text)
    union_number = Column(Text)

    # Datos laborales
    hire_date = Column(DATE)
    termination_date = Column(DATE)
    hire_type = Column(Text) # permanente, temporal, pasante
    work_location = Column(Text) # sucursal, oficina, remoto
    
    job_title = Column(Text)
    category = Column(Text)
    task = Column(Text)
    cost_center = Column(Text)
    union_agreement = Column(Text)

    # Datos previsionales (AFIP)
    pension_regime = Column(Text)
    activity = Column(Text)
    labor_condition = Column(Text)
    revista_situation = Column(Text)

    # Datos bancarios
    bank = Column(Text)
    bank_code = Column(Text)         # ISIS master bank code (1-18)
    bank_branch = Column(Text)       # ISIS branch code (sucursal)
    account_type = Column(Text)
    account_number = Column(Text)
    cbu = Column(Text)
    bank_alias = Column(Text)
    payment_method = Column(Text) # transferencia, efectivo, cheque
    payment_place = Column(Text)


    # GAP-TOKEN: Token-based invitation (Phase 2 Hardening)
    invite_token = Column(Text, unique=True, index=True)
    invite_token_expires_at = Column(TIMESTAMP(timezone=True))

    # GAP-IMPORT: Flexible data storage for unknown fields
    extra_fields = Column(JSONB, server_default=text("'{}'::jsonb"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    is_deleted = Column(Boolean, nullable=False, server_default=sa.text("false"))
    deleted_at = Column(TIMESTAMP(timezone=True))


    __table_args__ = (
        UniqueConstraint("organization_id", "dni", name="uq_employee_org_dni"),
        UniqueConstraint("organization_id", "cuil", name="uq_employee_org_cuil"),
        UniqueConstraint("organization_id", "file_number", name="uq_employee_org_legajo"),

        CheckConstraint("dni ~ '^[0-9]{7,8}$'", name="ck_employee_dni_format"),
        CheckConstraint("cuil IS NULL OR cuil ~ '^[0-9]{11}$'", name="ck_employee_cuil_format"),

        Index("idx_employee_org_dni", "organization_id", "dni"),
        Index("idx_employee_org_legajo", "organization_id", "file_number"),
        Index("idx_employees_extra_fields", "extra_fields", postgresql_using="gin"),
    )


# =====================================================
# COMPANY SIGNERS
# =====================================================
class CompanySigner(Base):
    __tablename__ = "company_signers"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    name = Column(Text, nullable=False)
    position = Column(Text, nullable=False)
    signature_image_path = Column(Text)
    is_active = Column(Boolean, nullable=False, server_default=text("true"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


# =====================================================
# PAYROLL BATCHES
# =====================================================
class PayrollBatch(Base):
    __tablename__ = "payroll_batches"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    period_label = Column(Text, nullable=False)

    source_pdf_path = Column(Text)
    source_pdf_sha256 = Column(CHAR(64))

    total_receipts = Column(Integer, nullable=False, server_default=text("0"))
    processed_receipts = Column(Integer, nullable=False, server_default=text("0"))

    uploaded_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("organization_id", "source_pdf_sha256", name="uq_batch_org_sha"),
    )


# =====================================================
# PAYROLL RECEIPTS
# =====================================================
class PayrollReceipt(Base):
    __tablename__ = "payroll_receipts"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    batch_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("payroll_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    employee_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("employees.id", ondelete="SET NULL"),
        index=True
    )

    page_number = Column(Integer, nullable=False)

    receipt_pdf_path = Column(Text, nullable=False)
    receipt_pdf_sha256 = Column(CHAR(64), nullable=False)

    extracted_fields = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    status = Column(
        SAEnum(ReceiptStatus, name="receipt_status", create_type=False),
        nullable=False,
        server_default=text("'pending_match'")
    )

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    signed_at = Column(TIMESTAMP(timezone=True))
    employer_signed_at = Column(TIMESTAMP(timezone=True))
    employee_signed_at = Column(TIMESTAMP(timezone=True))
    
    document_locked = Column(Boolean, nullable=False, server_default=text("false"))
    
    # GAP-019: Optional signatures
    requires_employer = Column(Boolean, nullable=False, server_default=text("true"))
    requires_employee = Column(Boolean, nullable=False, server_default=text("true"))
    
    # GAP-020: Verification ID for public QR
    verification_id = Column(Text, unique=True, index=True)

    # GAP-003: Processing flag for Phase 2/3 concurrency lock
    processing_signature = Column(Boolean, nullable=False, server_default=text("false"))

    # Phase 1 Fix: Atomic Forensic Snapshots (Level 10/10)
    signature_snapshot = Column(sa.LargeBinary)
    signature_hash = Column(String(64))
    
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Boolean, nullable=False, server_default=sa.text("false"))

    # ISIS: Payment receipt attachment (comprobante de pago)
    payment_receipt_path = Column(Text)
    payment_upload_date = Column(TIMESTAMP(timezone=True))
    payment_uploaded_by = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))

    # Employee Identity Snapshot (immutable after creation)
    # Preserves employee identity at receipt issuance time so that
    # deactivation, reactivation, or deletion does NOT affect historical display.
    snapshot_employee_name   = Column(Text)
    snapshot_employee_dni    = Column(Text)
    snapshot_employee_cuil   = Column(Text)
    snapshot_employee_legajo = Column(Text)
    snapshot_created_at      = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        Index("idx_receipt_org_status", "organization_id", "status"),
        Index("idx_receipt_org_employee", "organization_id", "employee_id"),
    )


# =====================================================
# SIGNATURE REQUESTS
# =====================================================
class SignatureRequest(Base):
    __tablename__ = "signature_requests"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("payroll_receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    enterprise_receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    employee_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    token_hash = Column(CHAR(64), nullable=False, unique=True)
    token_expires_at = Column(TIMESTAMP(timezone=True), nullable=False)

    status = Column(
        SAEnum(SignatureStatus, name="signature_status", create_type=False),
        nullable=False,
        server_default=text("'pending'")
    )

    document_source = Column(Text)
    issuer_ip = Column(INET)
    issuer_ua = Column(Text)
    issuer_user_id = Column(PG_UUID(as_uuid=False))
    requires_verification = Column(Boolean, server_default=text("true"))

    rejection_reason = Column(Text)

    requested_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    signed_at = Column(TIMESTAMP(timezone=True))


# =====================================================
# SIGNATURE EVIDENCE
# =====================================================
class SignatureEvidence(Base):
    __tablename__ = "signature_evidence"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    receipt_id = Column(PG_UUID(as_uuid=False), ForeignKey("payroll_receipts.id", ondelete="RESTRICT"), index=True)
    enterprise_receipt_id = Column(PG_UUID(as_uuid=False), ForeignKey("receipts.id", ondelete="RESTRICT"), index=True)
    verification_id = Column(Text, unique=True, index=True)

    signed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    acceptance_text = Column(Text, nullable=False)
    signer_full_name = Column(Text, nullable=False)
    signer_cuil = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)

    receipt_sha256_at_sign_time = Column(CHAR(64), nullable=False)

    signature_image_path = Column(Text, nullable=False)
    signature_image_sha256 = Column(CHAR(64), nullable=False)
    final_pdf_sha256 = Column(CHAR(64))

    # GAP-SIGN: Extended Metadata (Pro Executive Review)
    signer_user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"))
    batch_id = Column(PG_UUID(as_uuid=False), ForeignKey("payroll_batches.id", ondelete="SET NULL"))
    
    cert_fingerprint_sha256 = Column(Text)
    cert_serial = Column(Text)
    cert_issuer = Column(Text)
    cert_subject = Column(Text)
    cert_not_before = Column(TIMESTAMP(timezone=True))
    cert_not_after = Column(TIMESTAMP(timezone=True))
    
    signature_algorithm = Column(String(50))
    tsa_timestamp = Column(TIMESTAMP(timezone=True))
    sig_version = Column(String(50))
    validation_status = Column(String(50), server_default=text("'valid'"))
    ocsp_status = Column(String(20))
    ocsp_checked_at = Column(TIMESTAMP(timezone=True))
    crl_status = Column(String(20))
    crl_checked_at = Column(TIMESTAMP(timezone=True))
    validation_checked_at = Column(TIMESTAMP(timezone=True))
    validation_error = Column(Text)
    signing_method = Column(String(30), server_default=text("'Digital-PAdES-LTV'"))


# =====================================================
# SIGNING LOGS (Traceability)
# =====================================================
class SigningLog(Base):
    __tablename__ = "signing_logs"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(PG_UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    action = Column(String(50), nullable=False) # 'signature_start', 'signature_success', 'signature_failure'
    ip_address = Column(Text)
    user_agent = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    
    user = relationship("User")
# =====================================================
class SignatureEvent(Base):
    __tablename__ = "signature_events"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("payroll_receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    enterprise_receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    enterprise_receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    enterprise_receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    actor_type = Column(
        SAEnum(ActorType, name="actor_type", create_type=False),
        nullable=False
    )

    actor_id = Column(PG_UUID(as_uuid=False))

    action = Column(Text, nullable=False)

    status_before = Column(Text)
    status_after = Column(Text)

    pdf_sha256_before = Column(CHAR(64))
    pdf_sha256_after = Column(CHAR(64))

    ip_address = Column(INET)
    user_agent = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


# =====================================================
# RECEIPT SEALS (Inmutable Ledger of Sealing Events)
# =====================================================
class ReceiptSeal(Base):
    __tablename__ = "receipt_seals"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    
    seal_id = Column(Text, unique=True, index=True, nullable=False)
    
    # Can refer to either payroll_receipts or receipts (enterprise)
    receipt_id = Column(PG_UUID(as_uuid=False), nullable=False, index=True)
    organization_id = Column(PG_UUID(as_uuid=False), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    signer_dni = Column(Text, nullable=False)
    signer_name = Column(Text, nullable=False)
    signer_role = Column(Text, nullable=False) # 'employee' | 'employer'
    
    pdf_hash = Column(Text, nullable=False)
    metadata_json = Column(JSONB, server_default=text("'{}'::jsonb"), name="metadata")
    
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_seal_receipt_role", "receipt_id", "signer_role"),
    )


# =====================================================
# FILE ENCRYPTION METADATA
# =====================================================
class FileEncryptionMetadata(Base):
    __tablename__ = "file_encryption_metadata"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    file_id = Column(PG_UUID(as_uuid=False), nullable=False, unique=True, index=True)
    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_path = Column(Text, nullable=False)
    encrypted_data_key = Column(Text, nullable=False)
    nonce = Column(Text, nullable=False)
    auth_tag = Column(Text, nullable=False)
    algorithm = Column(String(32), nullable=False, server_default=text("'AES-256-GCM'"))
    kms_key_id = Column(Text, nullable=False)
    kms_provider = Column(String(32), nullable=False)
    purpose = Column(String(64), nullable=False)
    plaintext_sha256 = Column(CHAR(64))
    ciphertext_sha256 = Column(CHAR(64))
    encryption_context = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by = Column(PG_UUID(as_uuid=False))
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    last_decrypted_at = Column(TIMESTAMP(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "storage_path", name="uq_file_encryption_org_path"),
        CheckConstraint("algorithm = 'AES-256-GCM'", name="ck_file_encryption_algorithm"),
        Index("idx_file_encryption_purpose", "organization_id", "purpose"),
        Index("idx_file_encryption_storage_path", "storage_path"),
    )


# =====================================================
# WEBHOOK OUTBOX (Transactional Outbox Pattern)
# =====================================================
class WebhookOutbox(Base):
    __tablename__ = "webhook_outbox"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    idempotency_key = Column(CHAR(64), nullable=False, unique=True)

    receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("payroll_receipts.id", ondelete="CASCADE"),
        nullable=True,
    )
    enterprise_receipt_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=True,
    )
    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )

    action = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    status = Column(Text, nullable=False, server_default=text("'pending'"))
    retries = Column(Integer, nullable=False, server_default=text("0"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    delivered_at = Column(TIMESTAMP(timezone=True))
    next_attempt_at = Column(TIMESTAMP(timezone=True))
    last_error_at = Column(TIMESTAMP(timezone=True))


# =====================================================
# AUDIT LOG
# =====================================================
class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    organization_id = Column(PG_UUID(as_uuid=False), nullable=False, index=True)
    actor_type = Column(SAEnum(ActorType, name="actor_type", create_type=False), nullable=False)
    actor_id = Column(PG_UUID(as_uuid=False))

    action = Column(Text, nullable=False)
    entity_id = Column(PG_UUID(as_uuid=False))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    data = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
class EmailEvent(Base):
    __tablename__ = "email_events"
    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=func.uuid_generate_v4())
    receipt_id = Column(PG_UUID(as_uuid=False), ForeignKey("payroll_receipts.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(PG_UUID(as_uuid=False), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)  # sent, opened, signed, failed
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    opened_at = Column(DateTime(timezone=True))
    ip_address = Column(String(100))
    user_agent = Column(String(500))
    device_type = Column(String(20))  # mobile, tablet, desktop
    
    # Relationships
    receipt = relationship("PayrollReceipt")
    employee = relationship("Employee")


# =====================================================
# EMPLOYEE EXTRA DATA (Legajo Extended Fields â€” 1:1)
# =====================================================
class EmployeeExtraData(Base):
    __tablename__ = "employee_extra_data"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    employee_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # â”€â”€ Identity extended â”€â”€
    document_type_code = Column(Text)           # CÃ³digo tipo documento (1=DNI, etc.)
    anses_doc_issue_place_code = Column(Text)    # CÃ³digo ANSES lugar emisiÃ³n doc
    nationality_code = Column(Text)              # CÃ³digo nacionalidad
    marital_status_code = Column(Text)           # CÃ³digo estado civil
    sex_code = Column(Text)                      # CÃ³digo sexo (1=M, 2=V)

    # â”€â”€ Address granular â”€â”€
    street_number = Column(Text)
    floor = Column(Text)
    apartment = Column(Text)
    tower = Column(Text)
    paraje = Column(Text)                        # Barrio / paraje rural
    locality_code = Column(Text)
    province_code = Column(Text)

    # â”€â”€ Employment extended (codes AFIP/ANSES) â”€â”€
    category_code = Column(Text)
    section_code = Column(Text)
    task_code = Column(Text)
    position_code = Column(Text)
    activity_code = Column(Text)
    labor_condition_code = Column(Text)
    contract_mode_code = Column(Text)
    afip_revista_status_code = Column(Text)
    afip_locality_province_code = Column(Text)
    hazardous_task_code = Column(Text)
    workday_type_code = Column(Text)
    remuneration_type_code = Column(Text)
    payment_place_code = Column(Text)
    payroll_concept_group_code = Column(Text)
    assigned_monthly_hours = Column(Integer)

    # â”€â”€ Union / agreement â”€â”€
    union_agreement_code = Column(Text)
    agreement_type_code = Column(Text)
    union_member_number = Column(Text)

    # â”€â”€ Payroll / legacy identifiers â”€â”€
    legajo_number = Column(Text)                 # NÃºmero de legajo interno
    card_number = Column(Text)                   # NÃºmero de tarjeta
    ieric_number = Column(Text)                  # NÃºmero IERIC (construcciÃ³n)

    # â”€â”€ Social security â”€â”€
    health_insurance_code = Column(Text)         # CÃ³digo obra social
    social_work_code = Column(Text)              # Alias for health_insurance
    union_code = Column(Text)
    retirement_regime_code = Column(Text)        # CÃ³digo rÃ©gimen previsional
    unemployment_fund_account = Column(Text)     # Cuenta fondo de desempleo

    # â”€â”€ Payroll / Banking (Extended) â”€â”€
    salary_amount = Column(Numeric(precision=18, scale=2))
    salary_currency = Column(Text, server_default=text("'ARS'"))
    payment_method_code = Column(Text)
    bank_name = Column(Text)
    bank_branch = Column(Text)
    bank_cbu = Column(Text)
    bank_account_number = Column(Text)

    # â”€â”€ Mapping / Address missing â”€â”€
    address_street = Column(Text)
    address_city = Column(Text)
    address_province = Column(Text)
    address_zip_code = Column(Text)

    # â”€â”€ Import source metadata â”€â”€
    source_last_import_job_id = Column(PG_UUID(as_uuid=False))
    source_last_imported_at = Column(TIMESTAMP(timezone=True))
    source_last_format = Column(Text)            # xlsx | csv | txt
    source_hash = Column(Text)                   # Hash del row canÃ³nico importado

    # â”€â”€ Audit â”€â”€
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    employee = relationship("Employee", backref="extra_data", uselist=False)


# =====================================================
# IMPORT JOBS (Legajo Import Session Tracking)
# =====================================================
class ImportJob(Base):
    __tablename__ = "import_jobs"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    organization_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    # â”€â”€ Source info â”€â”€
    source_type = Column(Text, nullable=False)             # xlsx | csv | txt
    operation_type = Column(Text, nullable=False)          # preview | import | export
    original_filename = Column(Text)
    stored_file_path = Column(Text)
    file_sha256 = Column(CHAR(64))

    # â”€â”€ Versioning â”€â”€
    parser_version = Column(Text, server_default=text("'1'"))
    mapping_version = Column(Text, server_default=text("'1'"))
    validator_version = Column(Text, server_default=text("'1'"))

    # â”€â”€ Idempotency â”€â”€
    duplicate_of_job_id = Column(PG_UUID(as_uuid=False), ForeignKey("import_jobs.id", ondelete="SET NULL"))
    duplicate_group_id = Column(PG_UUID(as_uuid=False), index=True)

    # â”€â”€ Control â”€â”€
    import_mode = Column(Text, server_default=text("'merge'"))  # merge | replace
    dry_run = Column(Boolean, nullable=False, server_default=text("false"))

    status = Column(Text, nullable=False, server_default=text("'uploaded'"))

    # â”€â”€ Metrics â”€â”€
    total_rows = Column(Integer, server_default=text("0"))
    valid_rows = Column(Integer, server_default=text("0"))
    invalid_rows = Column(Integer, server_default=text("0"))
    warning_rows = Column(Integer, server_default=text("0"))
    inserted_count = Column(Integer, server_default=text("0"))
    updated_count = Column(Integer, server_default=text("0"))
    skipped_count = Column(Integer, server_default=text("0"))
    conflicted_count = Column(Integer, server_default=text("0"))
    failed_count = Column(Integer, server_default=text("0"))

    # â”€â”€ Timing â”€â”€
    started_at = Column(TIMESTAMP(timezone=True))
    finished_at = Column(TIMESTAMP(timezone=True))

    # â”€â”€ Diagnostics â”€â”€
    error_summary_json = Column(JSONB, server_default=text("'{}'::jsonb"))
    warning_summary_json = Column(JSONB, server_default=text("'{}'::jsonb"))
    metadata_json = Column(JSONB, server_default=text("'{}'::jsonb"))

    # â”€â”€ Audit â”€â”€
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())
    
    rows = relationship("ImportJobRow", back_populates="job", order_by="ImportJobRow.source_row_number", cascade="all, delete-orphan")

    # â”€â”€ Idempotency: same file for same org = duplicate â”€â”€
    __table_args__ = (
        UniqueConstraint("organization_id", "file_sha256", name="uq_import_job_org_sha"),
        Index("idx_import_job_org_created", "organization_id", "created_at"),
    )


# =====================================================
# IMPORT JOB ROWS (Per-Row Parse/Validation Result)
# =====================================================
class ImportJobRow(Base):
    __tablename__ = "import_job_rows"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))

    import_job_id = Column(
        PG_UUID(as_uuid=False),
        ForeignKey("import_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_row_number = Column(Integer, nullable=False)
    external_key = Column(Text)                            # e.g. DNI or legajo_number

    # â”€â”€ Data snapshots â”€â”€
    raw_data_json = Column(JSONB, server_default=text("'{}'::jsonb"))
    normalized_data_json = Column(JSONB, server_default=text("'{}'::jsonb"))

    # â”€â”€ Validation results â”€â”€
    validation_errors_json = Column(JSONB, server_default=text("'[]'::jsonb"))
    validation_warnings_json = Column(JSONB, server_default=text("'[]'::jsonb"))

    # â”€â”€ Matching â”€â”€
    matching_result_json = Column(JSONB, server_default=text("'{}'::jsonb"))
    planned_action = Column(Text)                          # insert | update | skip | conflict | invalid
    resolution_status = Column(Text, server_default=text("'pending'"))

    matched_employee_id = Column(PG_UUID(as_uuid=False))

    job = relationship("ImportJob", back_populates="rows")

    # â”€â”€ Audit â”€â”€
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_import_row_job_rownum", "import_job_id", "source_row_number"),
        Index("idx_import_row_job_action", "import_job_id", "planned_action"),
    )


# =====================================================
# NOTIFICATIONS
# =====================================================
class Notification(Base):
    __tablename__ = "notifications"

    id = Column(PG_UUID(as_uuid=False), primary_key=True, server_default=text("uuid_generate_v4()"))
    sender_user_id = Column(
        PG_UUID(as_uuid=False), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    # GAP-010: Recipient support for bidirectional messaging
    recipient_user_id = Column(
        PG_UUID(as_uuid=False), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=True, 
        index=True
    )
    company_id = Column(
        PG_UUID(as_uuid=False), 
        ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    message = Column(Text, nullable=False)
    file_path = Column(Text)
    is_read = Column(Boolean, nullable=False, server_default=text("false"))
    
    # GAP-010: Independent deletion
    is_deleted_by_sender = Column(Boolean, nullable=False, server_default=text("false"))
    is_deleted_by_recipient = Column(Boolean, nullable=False, server_default=text("false"))

    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())

    sender = relationship("User", foreign_keys=[sender_user_id])
    recipient = relationship("User", foreign_keys=[recipient_user_id])
