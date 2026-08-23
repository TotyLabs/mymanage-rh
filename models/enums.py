from enum import Enum


class ReceiptStatus(str, Enum):
    pending_match = "pending_match"
    processing = "processing"
    pending_signature = "pending_signature"
    pending_employee_signature = "pending_employee_signature"
    pending_employer_signature = "pending_employer_signature"
    signed = "signed"
    rejected = "rejected"


class SignatureStatus(str, Enum):
    pending = "pending"
    signed = "signed"
    rejected = "rejected"
    expired = "expired"


class ActorType(str, Enum):
    admin = "admin"
    employee = "employee"
    system = "system"


class UserRole(str, Enum):
    admin = "admin"
    employee = "employee"


class UserStatus(str, Enum):
    pending_verification = "pending_verification"
    active = "active"
    full = "full"
    lightweight = "lightweight"


class EmployeeStatus(str, Enum):
    pending_verification = "pending_verification"  # Auto-created from batch DNI, awaiting user validation
    pre_registered = "pre_registered"
    active = "active"
    inactive = "inactive"


# â”€â”€â”€ Legajo Import/Export System â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class ImportJobStatus(str, Enum):
    uploaded = "uploaded"
    parsed = "parsed"
    preview_ready = "preview_ready"
    queued = "queued"
    processing = "processing"
    importing = "importing"
    imported = "imported"
    simulated = "simulated"       # dry-run completed
    failed = "failed"


class ImportMode(str, Enum):
    merge = "merge"               # nulls don't overwrite existing data
    replace = "replace"           # file is full truth, nulls clear fields


class PlannedAction(str, Enum):
    insert = "insert"
    update = "update"
    skip = "skip"
    conflict = "conflict"
    invalid = "invalid"


class ResolutionStatus(str, Enum):
    pending = "pending"
    inserted = "inserted"
    updated = "updated"
    skipped = "skipped"
    conflicted = "conflicted"
    invalid = "invalid"
    simulated = "simulated"       # dry-run: no DB write
