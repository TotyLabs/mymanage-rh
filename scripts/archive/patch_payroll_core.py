"""Patch script: fix create_signature_request for enterprise receipts."""
import re

filepath = "payroll_core.py"
content = open(filepath, "r", encoding="utf-8").read()

# The old INSERT block (single f-string INSERT for both sources)
old_block = (
    '    db.execute(text(f"""\r\n'
    '        INSERT INTO signature_requests (\r\n'
    '            id, {rid_col}, employee_id, organization_id,\r\n'
    '            token_hash, token_expires_at, status, document_source\r\n'
    '        )\r\n'
    "        VALUES (uuid_generate_v4(), :receipt_id, :employee_id, :org_id, :token_hash, :expires_at, 'pending', :source)\r\n"
    '    """), {\r\n'
    '        "receipt_id": receipt_id,\r\n'
    '        "employee_id": employee_id,\r\n'
    '        "org_id": organization_id,\r\n'
    '        "token_hash": token_hash,\r\n'
    '        "expires_at": expires_at,\r\n'
    '        "source": source\r\n'
    '    })'
)

new_block = (
    '    if source == "enterprise":\r\n'
    '        # Enterprise: employee_id is NULL (receiver is a user, not an employees row)\r\n'
    '        db.execute(text("""\r\n'
    '            INSERT INTO signature_requests (\r\n'
    '                id, enterprise_receipt_id, organization_id,\r\n'
    '                token_hash, token_expires_at, status, document_source\r\n'
    '            )\r\n'
    "            VALUES (uuid_generate_v4(), :receipt_id, :org_id, :token_hash, :expires_at, 'pending', 'enterprise')\r\n"
    '        """), {\r\n'
    '            "receipt_id": receipt_id,\r\n'
    '            "org_id": organization_id,\r\n'
    '            "token_hash": token_hash,\r\n'
    '            "expires_at": expires_at,\r\n'
    '        })\r\n'
    '    else:\r\n'
    '        # Legacy payroll: employee_id FK is valid\r\n'
    '        db.execute(text("""\r\n'
    '            INSERT INTO signature_requests (\r\n'
    '                id, receipt_id, employee_id, organization_id,\r\n'
    '                token_hash, token_expires_at, status, document_source\r\n'
    '            )\r\n'
    "            VALUES (uuid_generate_v4(), :receipt_id, :employee_id, :org_id, :token_hash, :expires_at, 'pending', 'payroll')\r\n"
    '        """), {\r\n'
    '            "receipt_id": receipt_id,\r\n'
    '            "employee_id": employee_id,\r\n'
    '            "org_id": organization_id,\r\n'
    '            "token_hash": token_hash,\r\n'
    '            "expires_at": expires_at,\r\n'
    '        })'
)

if old_block in content:
    content = content.replace(old_block, new_block)
    open(filepath, "w", encoding="utf-8").write(content)
    print("OK - patched successfully")
else:
    print("ERROR - old block not found, dumping lines 800-815:")
    lines = content.split("\r\n")
    for i in range(799, min(815, len(lines))):
        print(f"  {i+1}: {repr(lines[i])}")
