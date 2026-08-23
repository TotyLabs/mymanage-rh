from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, or_, and_
from typing import List, Optional
import os
import uuid
from pathlib import Path
from datetime import datetime

from payroll_core import get_db, logger, require_auth, safe_join_under_storage
from models.tables import User, Notification, Organization
from services.email_service import EmailService
import config

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

@router.post("")
async def create_notification(
    message: str = Form(...),
    recipient_ids: Optional[str] = Form(None), # Optional: Comma-separated list. If null, sent to company admins
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    org_id = current_user["organization_id"]
    if not org_id:
        raise HTTPException(status_code=400, detail="User not linked to an organization")
        
    sender_id = current_user["id"]
    role = current_user.get("role")

    # Business Logic:
    # Employees send to Company (recipient_ids=None)
    # Admins send to specific Employees (recipient_ids required)
    
    target_users = []
    if role == "employee":
        target_users.append(None) # Employees always send to the "Company"
    elif role == "admin":
        if not recipient_ids:
            raise HTTPException(status_code=400, detail="Admins must specify at least one recipient employee")
        
        from models.tables import Employee
        raw_ids = [r.strip() for r in recipient_ids.split(",") if r.strip()]
        for tid in raw_ids:
            # Resolve each tid if it's an employee_id instead of user_id
            user_match = db.query(User).filter(User.id == tid).first()
            if not user_match:
                emp = db.query(Employee).filter(Employee.id == tid).first()
                if emp:
                    user_match = db.query(User).filter(User.employee_id == emp.id).first()
                    if user_match:
                        target_users.append(user_match.id)
                    else:
                        user_match = db.query(User).filter(
                            or_(User.username == emp.cuil, User.username == emp.dni)
                        ).first()
                        if user_match:
                            target_users.append(user_match.id)
                            user_match.employee_id = emp.id
                            db.commit()
                        else:
                            # Skip if no user account linked yet, or handle gracefully
                            continue
                else:
                    continue
            else:
                target_users.append(user_match.id)
                
        if not target_users:
            raise HTTPException(status_code=400, detail="No se encontraron destinatarios válidos.")

    batch_id = str(uuid.uuid4())
    file_path = None
    
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    if file:
        file_ext = os.path.splitext(file.filename)[1]
        relative_path = os.path.join("notifications", str(org_id), batch_id, f"attachment{file_ext}")
        safe_path = safe_join_under_storage(relative_path)
        
        os.makedirs(os.path.dirname(safe_path), exist_ok=True)
        with open(safe_path, "wb") as f:
            f.write(await file.read())
        file_path = relative_path

    for target_user_id in target_users:
        new_notification = Notification(
            id=str(uuid.uuid4()),
            sender_user_id=sender_id,
            recipient_user_id=target_user_id,
            company_id=org_id,
            message=message,
            file_path=file_path,
            is_read=False
        )
        db.add(new_notification)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.exception("notification.create_failed")
        raise HTTPException(status_code=500, detail="Database error")
        
    # Email alerting
    email_svc = EmailService()
    preview = message[:100] + ("..." if len(message) > 100 else "")
    sender_name = current_user.get("full_name") or current_user.get("email", "Usuario")
    
    if role == "admin":
        # Alert specific employees
        for target_user_id in target_users:
            target_user = db.query(User).filter(User.id == target_user_id).first()
            if target_user and target_user.email:
                await email_svc.send_employee_notification_alert(
                    to_email=target_user.email,
                    organization_name=org.name,
                    sender_name=sender_name,
                    message_preview=preview,
                )
    else:
        # Alert admins (Company notification)
        admins = db.query(User).filter(User.organization_id == org_id, User.role == "admin", User.is_active == True).all()
        admin_emails = [admin.email for admin in admins if admin.email]
        if org.email and org.email not in admin_emails:
            admin_emails.insert(0, org.email)
        
        if admin_emails:
            await email_svc.send_company_notification_alert(
                to_emails=admin_emails,
                organization_name=org.name,
                sender_name=sender_name,
                message_preview=preview
            )

    return {"status": "ok"}

@router.get("")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    org_id = current_user["organization_id"]
    user_id = current_user["id"]
    role = current_user["role"]
    
    # Query logic:
    # 1. Messages sent by me (and not deleted by me)
    # 2. Messages sent to me (and not deleted by me)
    # 3. If admin: Messages sent to the company (recipient is null)
    
    filters = []
    
    # Sent by me
    filters.append(and_(Notification.sender_user_id == user_id, Notification.is_deleted_by_sender == False))
    
    # Received by me
    filters.append(and_(Notification.recipient_user_id == user_id, Notification.is_deleted_by_recipient == False))
    
    if role == "admin":
        # Sent to company
        filters.append(and_(Notification.recipient_user_id == None, Notification.company_id == org_id, Notification.is_deleted_by_recipient == False))

    notifs = db.query(Notification).filter(or_(*filters)).order_by(Notification.created_at.desc()).all()
    
    result = []
    for n in notifs:
        # Fetch sender info
        sender = db.query(User).filter(User.id == n.sender_user_id).first()
        recipient = None
        if n.recipient_user_id:
            recipient = db.query(User).filter(User.id == n.recipient_user_id).first()

        result.append({
            "id": n.id,
            "sender_name": sender.full_name if sender else "Sistema",
            "sender_email": sender.email if sender else "",
            "recipient_name": recipient.full_name if recipient else "Empresa",
            "message": n.message,
            "has_file": bool(n.file_path),
            "is_read": n.is_read if n.recipient_user_id == user_id or (n.recipient_user_id is None and role == "admin") else True,
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "direction": "outbound" if n.sender_user_id == user_id else "inbound"
        })
        
    return {"status": "ok", "notifications": result}

@router.get("/unread-count")
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    user_id = current_user["id"]
    org_id = current_user["organization_id"]
    role = current_user["role"]
    
    filters = []
    # Unread messages sent to me
    filters.append(and_(Notification.recipient_user_id == user_id, Notification.is_read == False, Notification.is_deleted_by_recipient == False))
    
    if role == "admin":
        # Unread messages sent to company
        filters.append(and_(Notification.recipient_user_id == None, Notification.company_id == org_id, Notification.is_read == False, Notification.is_deleted_by_recipient == False))
        
    count = db.query(Notification).filter(or_(*filters)).count()
    return {"status": "ok", "count": count}

@router.post("/{notification_id}/read")
def mark_as_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    user_id = current_user["id"]
    role = current_user["role"]
    
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    # Check if user is the recipient
    is_recipient = (notif.recipient_user_id == user_id) or (notif.recipient_user_id is None and role == "admin")
    
    if is_recipient:
        notif.is_read = True
        db.commit()
    
    return {"status": "ok"}

@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    user_id = current_user["id"]
    role = current_user["role"]
    
    notif = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    # Independent deletion logic
    if notif.sender_user_id == user_id:
        notif.is_deleted_by_sender = True
    
    if (notif.recipient_user_id == user_id) or (notif.recipient_user_id is None and role == "admin"):
        notif.is_deleted_by_recipient = True
        
    db.commit()
    return {"status": "ok"}

@router.get("/{notification_id}/file")
def get_notification_file(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_auth)
):
    org_id = current_user["organization_id"]
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.company_id == org_id
    ).first()
    
    if not notif or not notif.file_path:
        raise HTTPException(status_code=404, detail="File not found")
        
    safe_path = safe_join_under_storage(notif.file_path)
    if not os.path.exists(safe_path):
        raise HTTPException(status_code=404, detail="File does not exist on disk")
        
    return FileResponse(safe_path)
