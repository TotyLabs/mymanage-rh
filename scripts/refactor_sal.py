import os
import re

FILES = [
    "api/employees.py",
    "api/receipts.py",
    "api/admin.py",
    "api/batches.py",
    "api/signatures.py"
]

def refactor_sal_calls():
    for filepath in FILES:
        if not os.path.exists(filepath):
            continue
            
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Refactor generic calls to ensure_org_owner (safe default for org-based resources)
        # We target cases that use "organization_id" or organization fields
        new_content = re.sub(
            r"SecurityAssertions\.ensure_owner\(([^,]+),\s*([^,]+),\s*\"organization_id\"\)",
            r"SecurityAssertions.ensure_org_owner(\1, \2, \"organization_id\")",
            content
        )
        
        # Also handle cases with only 2 arguments (defaults to organization_id)
        new_content = re.sub(
            r"SecurityAssertions\.ensure_owner\(([^,]+),\s*([^,)]+)\)",
            r"SecurityAssertions.ensure_org_owner(\1, \2)",
            new_content
        )
        
        if content != new_content:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Refactored organization calls in {filepath}")

if __name__ == "__main__":
    refactor_sal_calls()
