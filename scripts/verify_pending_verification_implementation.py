"""
Verification script to ensure all changes for pending_verification are in place.

Usage:
    python scripts/verify_pending_verification_implementation.py
"""

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_enum_definition():
    """Check if pending_verification is in EmployeeStatus enum"""
    try:
        from models.enums import EmployeeStatus
        
        statuses = list(EmployeeStatus)
        status_names = [s.value for s in statuses]
        
        if "pending_verification" in status_names:
            print("âœ… EmployeeStatus.pending_verification defined in enum")
            return True
        else:
            print(f"âŒ EmployeeStatus.pending_verification NOT found")
            print(f"   Available: {status_names}")
            return False
    except Exception as e:
        print(f"âŒ Error importing EmployeeStatus: {e}")
        return False


def check_api_endpoints():
    """Check if new API endpoints exist"""
    api_file = Path("api/employees.py")
    
    if not api_file.exists():
        print(f"âŒ {api_file} not found")
        return False
    
    try:
        content = api_file.read_text(encoding='utf-8')
    except:
        content = api_file.read_text()
    
    checks = {
        'pending-verification/list': 'GET endpoint for listing pending employees',
        'verify-and-activate': 'POST endpoint for activating pending employees',
        'bulk-import': 'POST endpoint for bulk import',
    }
    
    all_ok = True
    for endpoint_name, description in checks.items():
        if endpoint_name in content:
            print(f"âœ… Endpoint '{endpoint_name}' found - {description}")
        else:
            print(f"âŒ Endpoint '{endpoint_name}' NOT found - {description}")
            all_ok = False
    
    return all_ok


def check_script_updates():
    """Check if create_employees_from_batch.py is updated"""
    script_file = Path("scripts/create_employees_from_batch.py")
    
    if not script_file.exists():
        print(f"âŒ {script_file} not found")
        return False
    
    try:
        content = script_file.read_text(encoding='utf-8')
    except:
        content = script_file.read_text()
    
    checks = {
        'pending_verification': 'Uses pending_verification status',
        'auto_created_from_batch_dni': 'Sets correct status_reason',
        '[Pendiente verificar]': 'Uses correct placeholder name',
    }
    
    all_ok = True
    for check_str, description in checks.items():
        if check_str in content:
            print(f"âœ… Script check '{check_str}' - {description}")
        else:
            print(f"âŒ Script check '{check_str}' - {description}")
            all_ok = False
    
    return all_ok


def check_migration_script():
    """Check if migration script exists"""
    script_file = Path("scripts/migrate_add_pending_verification.py")
    
    if script_file.exists():
        print("âœ… Migration script exists")
        return True
    else:
        print("âŒ Migration script NOT found")
        return False


def check_documentation():
    """Check if documentation is updated"""
    doc_file = Path("docs/BULK_EMPLOYEE_IMPORT.md")
    impl_file = Path("IMPLEMENTATION_PENDING_VERIFICATION.md")
    
    all_ok = True
    
    for doc_path in [doc_file, impl_file]:
        if doc_path.exists():
            try:
                content = doc_path.read_text(encoding='utf-8')
            except:
                try:
                    content = doc_path.read_text(encoding='latin-1')
                except:
                    content = doc_path.read_text()
            
            if 'pending_verification' in content:
                print(f"âœ… Documentation updated: {doc_path}")
            else:
                print(f"âš ï¸  Documentation exists but pending_verification not mentioned: {doc_path}")
        else:
            print(f"âš ï¸  Documentation not found: {doc_path} (optional)")
    
    return True


def verify_database_schema():
    """Check if database has the new status (requires DB connection)"""
    try:
        from payroll_core import get_db
        from sqlalchemy import text
        
        db = next(get_db())
        
        result = db.execute(text("""
            SELECT 1 FROM pg_enum 
            WHERE enumlabel = 'pending_verification' 
            AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'employee_status')
        """)).fetchone()
        
        db.close()
        
        if result:
            print("âœ… Database enum includes pending_verification")
            return True
        else:
            print("âš ï¸  Database enum does NOT include pending_verification")
            print("   Run: python scripts/migrate_add_pending_verification.py")
            return False
            
    except Exception as e:
        print(f"âš ï¸  Could not verify database schema: {e}")
        print("   This is OK if database is not running yet")
        return None


if __name__ == "__main__":
    print("=" * 70)
    print("VERIFICATION: Auto-create Controlado Implementation")
    print("=" * 70)
    print()
    
    checks = {
        "Enum Definition": check_enum_definition,
        "API Endpoints": check_api_endpoints,
        "Script Updates": check_script_updates,
        "Migration Script": check_migration_script,
        "Documentation": check_documentation,
    }
    
    results = {}
    for check_name, check_func in checks.items():
        print(f"\nðŸ“‹ {check_name}:")
        print("-" * 70)
        results[check_name] = check_func()
    
    # Database check separately since it might fail if DB isn't running
    print(f"\nðŸ“‹ Database Schema:")
    print("-" * 70)
    db_result = verify_database_schema()
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    success_count = sum(1 for v in results.values() if v)
    total_count = len(results)
    
    for check_name, result in results.items():
        status = "âœ…" if result else "âŒ"
        print(f"{status} {check_name}")
    
    if db_result is not None:
        status = "âœ…" if db_result else "âš ï¸ "
        print(f"{status} Database Schema")
    
    print()
    print(f"Checks passed: {success_count}/{total_count}")
    
    if success_count == total_count:
        print("\nðŸŽ‰ All checks passed! Implementation is complete.")
        print("\nNext steps:")
        print("1. Run: python scripts/migrate_add_pending_verification.py")
        print("2. Restart application: python main.py")
        print("3. Create employees: python scripts/create_employees_from_batch.py ...")
        sys.exit(0)
    else:
        print(f"\nâš ï¸  {total_count - success_count} check(s) failed. Review above.")
        sys.exit(1)
