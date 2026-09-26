"""
Auth API - Refactored v5.2
Flow: HR pre-registers (Name/DNI/CUIL) -> User completes profile during registration.

GAP-004: register_employee now creates signature_requests for linked receipts.
GAP-018: login endpoint is fully implemented.
"""

import re
from datetime import date
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, Response, Depends, HTTPException, Cookie, BackgroundTasks
try:
    from pydantic import BaseModel, Field, field_validator, EmailStr
except ImportError:
    # Fallback for Pydantic V1
    from pydantic import BaseModel, Field, validator as field_validator, EmailStr
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from payroll_core import (
    get_db, require_auth, limiter, hash_password, verify_password,
    create_session, create_signature_request, audit, hash_token, utc_now,
    normalize_org_name, normalize_cuil, PRODUCTION, SESSION_TTL_HOURS,
    logger, safe_transaction, validate_email_format, sanitize_text_input, SIGNATURE_MODE,
    normalize_dni, purge_user_sessions, delete_session_by_hash
)
from payroll_utils import get_real_ip
from services.verification_service import VerificationService
from services.email_service import EmailService
from services.sms_service import SmsService
from metrics.registry import metrics_registry

router = APIRouter(prefix="/api/auth", tags=["auth"])

# =========================================================
# VALIDATION HELPERS
# =========================================================

def normalize_full_name(name: str) -> str:
    name = sanitize_text_input(name)
    return re.sub(r"\s+", " ", name.strip())


async def trigger_registration_otp(email: str, phone: Optional[str], org_name: str, ip_address: str):
    """
    Triggers an OTP verification code for a new user.
    Harden: Does not raise exceptions if delivery fails, just logs it.
    """
    from payroll_core import SessionLocal
    db = SessionLocal()
    try:
        channel = "sms" if phone else "email"
        destination = phone if phone else email

        raw_code, status = VerificationService.create_code(
            db, email, ip_address,
            channel=channel,
            destination=destination,
            context="registration"
        )

        if status == "ok":
            db.commit()  # IMPORTANT: Commit the new code to DB
            if channel == "sms":
                SmsService().send_otp(phone, raw_code, org_name)
            else:
                await EmailService().send_verification_otp_email(email, raw_code, org_name)
            logger.info(f"auth.otp_triggered: email={email} channel={channel}")
        else:
            logger.warning(f"auth.otp_creation_failed: email={email} status={status}")
    except Exception as e:
        db.rollback()
        logger.error(f"auth.otp_delivery_exception: email={email} error={e}")
    finally:
        db.close()



# =========================================================
# SCHEMAS
# =========================================================

class LoginEmpresaRequest(BaseModel):
    clave: str = Field(..., min_length=8)

class EmployeeRegisterRequest(BaseModel):
    # Datos de Cuenta
    email: Optional[str] = None
    password: str = Field(..., min_length=8)

    # Identidad Core (con Token de InvitaciÃƒÂ³n opcional)
    invite_token: Optional[str] = Field(None, description="Token de invitaciÃƒÂ³n enviado por el empleador (Opcional)")
    dni: str = Field(..., min_length=7, max_length=9)
    cuil: str
    organization_id: Optional[str] = Field(None, description="UUID de la organizaciÃƒÂ³n (Opcional)")

    # Datos bÃƒÂ¡sicos del empleado
    full_name: str
    birth_date: date

    # Datos opcionales (el legajo completo lo gestiona RRHH)
    marital_status: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None

    @field_validator("birth_date")
    @classmethod
    def check_age(cls, v: date):
        if (date.today() - v).days < 18 * 365:
            raise ValueError("Debes ser mayor de 18 aÃƒÂ±os")
        return v


class LoginRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: str = Field(..., min_length=1)

    @field_validator('username', 'email', mode='before')
    @classmethod
    def sanitize_identifier(cls, v):
        if v is None: return v
        return str(v).strip().replace('\ufeff', '')

# =========================================================
# LOGIN EMPRESA
# =========================================================

@router.post("/login-empresa")
@limiter.limit("5/minute")
async def login_empresa(
    request: Request,
    body: LoginEmpresaRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Login exclusivo para empresas mediante Clave de Acceso (Token al portador).
    """
    clave_hash = hash_token(body.clave)
    ip = get_real_ip(request)
    prefix = body.clave[:8]

    # Buscar la clave en registration_keys
    key_record = db.execute(text("""
        SELECT id, is_active, is_revoked, used_by_org_id 
        FROM registration_keys 
        WHERE key_hash = :hash
    """), {"hash": clave_hash}).fetchone()

    if not key_record or not key_record.is_active or key_record.is_revoked:
        # Debug logging
        logger.warning(
            f"auth.login_empresa.invalid_key: ip={ip} prefix={prefix} hash={clave_hash[:10]}..."
        )
        metrics_registry.record_auth(success=False, rate_limit=False, token_invalid=True)
        # Prevención de ataques de tiempo
        import time; time.sleep(0.5)
        raise HTTPException(401, "invalid_credentials")

    org_id = key_record.used_by_org_id
    if not org_id:
        logger.error(f"auth.login_empresa.no_org: key_id={key_record.id}")
        raise HTTPException(401, "invalid_credentials")

    # Obtener el Usuario Administrador asociado a esta empresa
    user = db.execute(text("""
        SELECT id, role, is_active, user_status 
        FROM users 
        WHERE organization_id = :org_id AND role = 'admin' 
        LIMIT 1
    """), {"org_id": org_id}).fetchone()

    if not user or not user.is_active or user.user_status == 'deleted':
        logger.warning(f"auth.login_empresa.inactive_user: org={org_id}")
        raise HTTPException(401, "invalid_credentials")

    user_id = str(user.id)

    with safe_transaction(db):
        # 1. Invalidate previous sessions
        purge_user_sessions(db, user_id)
        
        # 2. Create new session (Standardized)
        token = create_session(db, user_id, request)
        
        # 3. Log audit
        prefix = body.clave[:8]
        audit(
            db, str(org_id), user.role, user_id,
            "LOGIN_EMPRESA_SUCCESS", user_id,
            {"ip": ip, "key_prefix": prefix}
        )

    # Configurar cookie segura HttpOnly (Standard session cookie)
    is_secure = PRODUCTION or request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        "session",
        token,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        max_age=SESSION_TTL_HOURS * 3600
    )

    return {
        "status": "success",
        "session_token": token,
        "user": {
            "id": user_id,
            "role": user.role
        }
    }



# =========================================================
# REGISTRO DE EMPLEADO (LÃƒÂ³gica de Match y Auto-completado)
# =========================================================

@router.post("/register-employee")
@limiter.limit("5/minute")
async def register_employee(
    request: Request,
    body: EmployeeRegisterRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Match determinístico por DNI.
    Si RRHH precargó el DNI, el usuario completa el resto de su perfil.
    GAP-004: After linking orphan receipts, signature_requests are created.
    """
    clean_dni = normalize_dni(body.dni)
    norm_cuil = normalize_cuil(body.cuil)
    clean_name = normalize_full_name(body.full_name)

    # --- RESOLUCIÓN DE ORGANIZATION_ID (Opcional) ---
    target_org_id = body.organization_id
    
    if not target_org_id:
        # Intento 1: Disambiguación por invite_token si existe
        if body.invite_token:
            token_match = db.execute(text("""
                SELECT organization_id FROM employees 
                WHERE invite_token = :token AND dni = :dni AND is_deleted = false
            """), {"token": body.invite_token, "dni": clean_dni}).fetchone()
            if token_match:
                target_org_id = token_match.organization_id

        # Intento 2: Auto-match por DNI + CUIL (desambiguación fuerte)
        if not target_org_id:
            # Seleccionamos también created_at para desempatar silenciosamente
            matches = db.execute(text("""
                SELECT e.organization_id, o.name as organization_name, e.created_at
                FROM employees e
                JOIN organizations o ON o.id = e.organization_id
                WHERE e.dni = :dni AND (e.cuil = :cuil OR e.cuil IS NULL)
                  AND e.status = 'pre_registered' AND e.is_deleted = false
                ORDER BY e.created_at DESC
            """), {"dni": clean_dni, "cuil": norm_cuil}).fetchall()
            
            if len(matches) >= 1:
                # AUTO-PURGE: Seleccionamos el más reciente sin preguntar al usuario
                target_org_id = matches[0].organization_id
            else:
                active_match = db.execute(text("""
                    SELECT 1 FROM employees
                    WHERE dni = :dni AND status = 'active' AND is_deleted = false
                    LIMIT 1
                """), {"dni": clean_dni}).fetchone()
                if active_match:
                    raise HTTPException(403, "dni_ya_activo")
                raise HTTPException(403, "dni_no_encontrado")

    # --- FLUJO CORE (Sin modificaciones) ---
    
    # GAP-INVITE-FIX: Búsqueda del registro pre-cargado
    if body.invite_token:
        emp = db.execute(text("""
            SELECT id, organization_id, status, email as pre_email
            FROM employees
            WHERE invite_token = :token AND dni = :dni AND organization_id = :org_id
              AND invite_token_expires_at > :now AND is_deleted = false
        """), {"token": body.invite_token, "dni": clean_dni, "org_id": target_org_id, "now": utc_now()}).fetchone()
    else:
        emp = db.execute(text("""
            SELECT id, organization_id, status, email as pre_email
            FROM employees
            WHERE dni = :dni AND organization_id = :org_id
              AND status = 'pre_registered' AND is_deleted = false
        """), {"dni": clean_dni, "org_id": target_org_id}).fetchone()

    if not emp:
        raise HTTPException(403, "registro_no_permitido_o_invitacion_invalida")

    # Create a synthetic email if none is provided
    provided_email = body.email.strip() if isinstance(body.email, str) and body.email.strip() else None
    final_email = provided_email if provided_email else f"{clean_dni}@sin-correo.local"

    if db.execute(text("SELECT 1 FROM users WHERE email = :e AND organization_id = :org_id"),
                  {"e": final_email, "org_id": emp.organization_id}).fetchone():
        raise HTTPException(409, "email_ya_registrado")

    try:
        with safe_transaction(db):
            # 2. ACTUALIZAR LEGAJO
            name_parts = clean_name.split(None, 1)
            fname = name_parts[0]
            lname = name_parts[1] if len(name_parts) > 1 else ""

            db.execute(text("""
                UPDATE employees SET
                    email = :e, cuil = :c, first_name = :fn, last_name = :ln,
                    birth_date = :bd, marital_status = :ms, address = :addr, phone = :ph,
                    status = 'active', profile_completed = true
                WHERE id = :id
            """), {
                "e": final_email, "c": norm_cuil, "fn": fname, "ln": lname,
                "bd": body.birth_date, "ms": body.marital_status,
                "addr": body.address, "ph": body.phone, "id": emp.id
            })

            # 2.5 INVALIDAR TOKEN
            db.execute(text("UPDATE employees SET invite_token = NULL, invite_token_expires_at = NULL WHERE id = :id"), {"id": emp.id})

            # 3. CREAR O RE-VINCULAR USUARIO DE ACCESO
            existing_free_user = db.execute(text("""
                SELECT id FROM users WHERE email = :e AND organization_id IS NULL
            """), {"e": final_email}).fetchone()

            phash = hash_password(body.password)
            if existing_free_user:
                # RE-VINCULAR usuario existente que estaba "libre"
                user_id = existing_free_user.id
                db.execute(text("""
                    UPDATE users SET
                        organization_id = :oid,
                        employee_id = :eid,
                        password_hash = :p,
                        full_name = :n,
                        user_status = :status,
                        is_verified = :verified,
                        is_active = true
                    WHERE id = :uid
                """), {
                    "oid": emp.organization_id, "eid": emp.id, "p": phash, "n": clean_name,
                    "status": "pending_verification", "verified": False, "uid": user_id
                })
                logger.info(f"auth.register.reusing_free_user: user_id={user_id} email={final_email}")
            else:
                # CREAR nuevo usuario
                user_res = db.execute(text("""
                    INSERT INTO users (
                        email, password_hash, full_name, role, organization_id, 
                        employee_id, user_status, is_verified
                    )
                    VALUES (:e, :p, :n, 'employee', :oid, :eid, :status, :verified)
                    RETURNING id
                """), {
                    "e": final_email, "p": phash, "n": clean_name,
                    "oid": emp.organization_id, "eid": emp.id,
                    "status": "pending_verification", "verified": False
                })
                user_id = user_res.fetchone().id

            # 3.1 Trigger OTP in background
            org_name = db.execute(text("SELECT name FROM organizations WHERE id = :oid"), {"oid": emp.organization_id}).scalar()
            background_tasks.add_task(
                trigger_registration_otp, final_email, body.phone, org_name, get_real_ip(request)
            )

            db.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": str(user_id)})

            # 4. VINCULACIÓN DE RECIBOS PENDIENTES (GAP-004)
            linked_receipts = db.execute(text("""
                UPDATE payroll_receipts
                SET employee_id = :eid, 
                    status = (CASE 
                        WHEN :sig_mode = 'dual' AND employer_signed_at IS NULL THEN 'pending_employer_signature'
                        ELSE 'pending_employer_signature'
                    END)::receipt_status
                WHERE organization_id = :oid
                  AND employee_id IS NULL
                  AND (extracted_fields->>'dni' = :dni OR extracted_fields->>'cuil' = :cuil)
                RETURNING id
            """), {
                "eid": emp.id, "oid": emp.organization_id, "dni": clean_dni, "cuil": norm_cuil, "sig_mode": SIGNATURE_MODE,
            }).fetchall()

            for r_row in linked_receipts:
                create_signature_request(db, str(r_row.id), str(emp.organization_id), str(emp.id))

            token = create_session(db, str(user_id), request)
            audit(db, emp.organization_id, "employee", user_id, "REGISTER_COMPLETE",
                  str(emp.id), {"linked_receipts": len(linked_receipts)})

        is_secure = PRODUCTION or request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
        response.set_cookie(
            "session", token,
            httponly=True, secure=is_secure, samesite="strict",
            max_age=SESSION_TTL_HOURS * 3600
        )

        return {
            "status": "success",
            "message": "Perfil completado y cuenta activada",
            "user": {"id": str(user_id), "email": body.email},
            "linked_receipts": len(linked_receipts),
        }

    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(409, "email_o_cuil_ya_registrado")
    except Exception as e:
        logger.error(f"Error en registro/match de empleado: {e}")
        raise HTTPException(500, "error_procesando_registro")


class LightweightRegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    full_name: str
    dni: str
    cuil: str
    organization_id: str

@router.post("/register-lightweight")
@limiter.limit("5/minute")
async def register_lightweight(
    request: Request,
    body: LightweightRegisterRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Phase 46: Lightweight registration for 'no account' signers.
    Creates a 'lightweight' user tied to an existing or new employee.
    """
    clean_dni = normalize_dni(body.dni)
    norm_cuil = normalize_cuil(body.cuil)
    clean_name = normalize_full_name(body.full_name)

    # 1. Check if employee already exists in org
    emp = db.execute(text("""
        SELECT id, organization_id FROM employees 
        WHERE organization_id = :oid AND (dni = :dni OR cuil = :cuil) AND is_deleted = false
    """), {"oid": body.organization_id, "dni": clean_dni, "cuil": norm_cuil}).fetchone()

    try:
        with safe_transaction(db):
            if not emp:
                # Create minimal employee record
                name_parts = clean_name.split(None, 1)
                fname = name_parts[0]
                lname = name_parts[1] if len(name_parts) > 1 else ""
                
                emp_res = db.execute(text("""
                    INSERT INTO employees (organization_id, first_name, last_name, dni, cuil, status)
                    VALUES (:oid, :fn, :ln, :dni, :cuil, 'pre_registered')
                    RETURNING id
                """), {
                    "oid": body.organization_id, "fn": fname, "ln": lname, 
                    "dni": clean_dni, "cuil": norm_cuil
                })
                emp_id = emp_res.fetchone().id
            else:
                emp_id = emp.id

            # 2. Check if user already exists
            if db.execute(text("SELECT 1 FROM users WHERE email = :e AND organization_id = :oid"),
                          {"e": body.email, "oid": body.organization_id}).fetchone():
                raise HTTPException(409, "email_already_registered")

            # 3. CREAR O RE-VINCULAR USUARIO 'LIGHTWEIGHT'
            existing_free_user = db.execute(text("""
                SELECT id FROM users WHERE email = :e AND organization_id IS NULL
            """), {"e": body.email}).fetchone()

            phash = hash_password(body.password)
            if existing_free_user:
                user_id = existing_free_user.id
                db.execute(text("""
                    UPDATE users SET
                        organization_id = :oid,
                        employee_id = :eid,
                        password_hash = :p,
                        full_name = :n,
                        user_status = 'pending_verification',
                        is_verified = false,
                        is_active = true
                    WHERE id = :uid
                """), {
                    "oid": body.organization_id, "eid": emp_id, "p": phash, "n": clean_name,
                    "uid": user_id
                })
            else:
                user_res = db.execute(text("""
                    INSERT INTO users (
                        email, password_hash, full_name, role, organization_id, 
                        employee_id, user_status, is_verified
                    )
                    VALUES (:e, :p, :n, 'employee', :oid, :eid, 'pending_verification', false)
                    RETURNING id
                """), {
                    "e": body.email, "p": phash, "n": clean_name,
                    "oid": body.organization_id, "eid": emp_id
                })
                user_id = user_res.fetchone().id

            # 3.1 Trigger OTP in background
            org_name = db.execute(text("SELECT name FROM organizations WHERE id = :oid"), {"oid": body.organization_id}).scalar()
            background_tasks.add_task(
                trigger_registration_otp, body.email, None, org_name, get_real_ip(request)
            )

            token = create_session(db, str(user_id), request)
            audit(db, body.organization_id, "employee", user_id, "REGISTER_LIGHTWEIGHT", str(emp_id), {})

        # Set cookie
        is_secure = PRODUCTION or request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
        response.set_cookie(
            "session", token,
            httponly=True, secure=is_secure, samesite="strict",
            max_age=SESSION_TTL_HOURS * 3600
        )

        return {
            "status": "success",
            "message": "Registro liviano completado",
            "user": {"id": str(user_id), "email": body.email, "status": "lightweight"}
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in lightweight registration: {e}")
        raise HTTPException(500, "error_procesando_registro_liviano")

# =========================================================
# LOGIN
# =========================================================

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    GAP-018: Fully implemented login endpoint.
    Verifies password with bcrypt, creates session cookie.
    """
    identifier = body.username or body.email
    if not identifier:
        raise HTTPException(400, "identificador_requerido")

    row = db.execute(text("""
        SELECT u.id, u.email, u.password_hash, u.role, u.is_active,
               u.organization_id, u.employee_id, u.full_name, u.user_status,
               u.failed_login_attempts, u.locked_until
        FROM users u
        LEFT JOIN employees e ON u.employee_id = e.id
        WHERE u.email = :identifier OR e.dni = :identifier OR e.phone = :identifier
    """), {"identifier": identifier}).fetchone()

    if not row:
        metrics_registry.record_auth(success=False, rate_limit=False, token_invalid=False)
        raise HTTPException(401, "credenciales_invalidas")

    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    
    if row.locked_until and row.locked_until.replace(tzinfo=timezone.utc) > now:
        metrics_registry.record_auth(success=False, rate_limit=True, token_invalid=False)
        raise HTTPException(403, "cuenta_bloqueada_temporalmente_por_multiples_intentos")

    if not verify_password(body.password, row.password_hash):
        with safe_transaction(db):
            attempts = (row.failed_login_attempts or 0) + 1
            locked_until = now + timedelta(minutes=15) if attempts >= 5 else None
            db.execute(text("""
                UPDATE users SET failed_login_attempts = :attempts, locked_until = :locked_until
                WHERE id = :id
            """), {"attempts": attempts, "locked_until": locked_until, "id": row.id})
            
            if attempts >= 5:
                logger.warning(f"auth.brute_force_lockout: user={row.id} ip={get_real_ip(request)}")
        metrics_registry.record_auth(success=False, rate_limit=False, token_invalid=False)
        raise HTTPException(401, "credenciales_invalidas")

    if not row.is_active:
        raise HTTPException(403, "cuenta_desactivada")

    if row.user_status != "active":
        metrics_registry.record_auth(success=False, rate_limit=False, token_invalid=False)
        raise HTTPException(403, "cuenta_no_verificada")

    with safe_transaction(db):
        db.execute(text("UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = :id"), {"id": row.id})
        db.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": str(row.id)})
        db.execute(text("""
            UPDATE users SET last_login = :now WHERE id = :id
        """), {"now": utc_now(), "id": row.id})

    token = create_session(db, str(row.id), request)
    metrics_registry.record_auth(success=True, rate_limit=False, token_invalid=False)

    with safe_transaction(db):
        org_id = str(row.organization_id) if row.organization_id is not None else None
        audit(db, org_id, "employee" if row.role == "employee" else "admin",
              str(row.id), "LOGIN", str(row.id), {"ip": get_real_ip(request)})

    is_secure = PRODUCTION or request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        "session", token,
        httponly=True,
        secure=is_secure,
        samesite="strict",
        max_age=SESSION_TTL_HOURS * 3600
    )

    return {
        "status": "success",
        "user": {
            "id": str(row.id),
            "email": row.email,
            "role": row.role,
            "full_name": row.full_name,
            "user_status": row.user_status,
        }
    }


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    session_token: Optional[str] = Cookie(default=None, alias="session"),
):
    """Invalidates the current session."""
    tokens = [session_token]
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        tokens.append(auth_header[len("Bearer "):].strip())
    tokens.extend((request.headers.get("X-Session-Token"), request.headers.get("X-Auth-Token")))

    for token in dict.fromkeys(value for value in tokens if value):
        token_hash = hash_token(token)
        try:
            with safe_transaction(db):
                result = db.execute(text("""
                    DELETE FROM user_sessions WHERE session_token_hash = :h
                    RETURNING user_id
                """), {"h": token_hash})
                row = result.fetchone()
                user_id = str(row.user_id) if row and row.user_id else None
        except Exception:
            logger.exception("auth.logout_session_delete_failed")
            raise HTTPException(500, "logout_failed")
        try:
            delete_session_by_hash(token_hash, user_id)
        except Exception:
            logger.exception("auth.logout_cache_delete_failed")

    response.delete_cookie("session")
    return {"status": "logged_out"}


@router.get("/me")
async def get_me(user=Depends(require_auth)):
    return {"user": user}

class AcceptTOSRequest(BaseModel):
    tos_version: str

@router.post("/accept-tos")
async def accept_tos(
    body: AcceptTOSRequest,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
    request: Request = None
):
    """
    Persists TOS acceptance for the authenticated user.
    """
    try:
        with safe_transaction(db):
            db.execute(text("""
                UPDATE users 
                SET tos_accepted = true, 
                    tos_accepted_at = :now, 
                    tos_version = :v,
                    tos_accept_ip = :ip
                WHERE id = :uid
            """), {
                "now": utc_now(),
                "v": body.tos_version,
                "ip": get_real_ip(request),
                "uid": user["id"]
            })
            audit(db, user["organization_id"], user["role"], user["id"], "TOS_ACCEPTED", user["id"], {"version": body.tos_version})
        return {"status": "success"}
    except Exception as e:
        logger.error(f"auth.accept_tos_failed: {e}")
        raise HTTPException(500, "error_accepting_tos")
