import pathlib

path = pathlib.Path('modules/digital_signature.py')
content = path.read_text(encoding='utf-8')

old_block_1 = '''            # GAP 2.b: Persist the first signature image an employee provides for future reuse
            db.execute(text("""
                UPDATE employees
                SET signature_image_path = :sig_path
                WHERE id = :emp_id AND signature_image_path IS NULL
            """), {
                "sig_path": str(pdf_result["sig_image_path"].relative_to(STORAGE_ROOT)),
                "emp_id": ctx["employee_id"]
            })'''

new_block_1 = '            # GAP 2.b: Auto-save removed. User must explicitly create their signature in Mi Firma.'

if old_block_1 in content:
    content = content.replace(old_block_1, new_block_1)
    print('Replaced block 1')
else:
    print('Block 1 not found')

old_block_2 = '''    # Resolve signature image (canvas vs stored)
    if body.signature_image == "STORED_SIGNATURE":
        # GAP 2 (Security): Strict ownership validation per design:
        # compare the signature request targeted employee with the current authenticated user's employee link
        if str(data["employee_id"]) != str(user.get("employee_id", "")):
            logger.error(f"signature_hijack_attempt: {user.get('id')} / {user.get('email')} tried to use stored signature of employee {data['employee_id']}")
            raise HTTPException(403, "no_puedes_usar_firma_de_otro_usuario")

        # Fetch stored signature path
        emp_row = db.execute(
            text("SELECT signature_image_path FROM employees WHERE id = :id"),
            {"id": data["employee_id"]}
        ).fetchone()
        
        if not emp_row or not emp_row.signature_image_path:
            raise HTTPException(400, "no_hay_firma_guardada")
            
        sig_path = Path(emp_row.signature_image_path)
        if not sig_path.exists():
            raise HTTPException(400, "archivo_de_firma_perdido")
            
        sig_image_bytes = sig_path.read_bytes()'''

new_block_2 = '''    # Resolve signature image (canvas vs stored)
    if body.signature_image == "STORED_SIGNATURE":
        # Fetch from user_signatures
        user_id = user["id"]
        
        if str(data["employee_id"]) != str(user.get("employee_id", "")):
            logger.error(f"signature_hijack_attempt: {user_id} tried to use stored signature for employee {data['employee_id']}")
            raise HTTPException(403, "no_puedes_usar_firma_de_otro_usuario")

        sig_row = db.execute(
            text("SELECT signature_path FROM user_signatures WHERE user_id = :id AND is_active = true ORDER BY created_at DESC LIMIT 1"),
            {"id": user_id}
        ).fetchone()
        
        if not sig_row or not sig_row.signature_path:
            raise HTTPException(400, "signature_required")
            
        sig_path = Path(sig_row.signature_path)
        if not sig_path.exists():
            raise HTTPException(400, "archivo_de_firma_perdido")
            
        sig_image_bytes = sig_path.read_bytes()'''

if old_block_2 in content:
    content = content.replace(old_block_2, new_block_2)
    print('Replaced block 2')
else:
    print('Block 2 not found')

path.write_text(content, encoding='utf-8')
