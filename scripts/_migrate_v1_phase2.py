"""
DB migration - Create company_signers table (Phase 2)
"""
import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from payroll_core import SessionLocal


def migrate():
    db = SessionLocal()
    try:
        # Check if table exists
        res = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'company_signers'
            );
        """)).fetchone()

        if not res[0]:
            print("Creating company_signers table...")
            db.execute(text("""
                CREATE TABLE company_signers (
                    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
                    name TEXT NOT NULL,
                    position TEXT NOT NULL,
                    signature_image_path TEXT,
                    is_active BOOLEAN NOT NULL DEFAULT true,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                CREATE INDEX idx_company_signers_org ON company_signers(organization_id);
            """))
            db.commit()
            print("Done: company_signers table created.")
        else:
            print("company_signers table already exists.")

        print("Phase 2 migration complete.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
