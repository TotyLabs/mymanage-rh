
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def migrate():
    print(f"Connecting to {DATABASE_URL}...")
    with engine.begin() as conn:
        print("Adding updated_at to receipts...")
        try:
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"))
            print("  Done.")
        except Exception as e:
            print(f"  Error: {e}")

        print("Adding updated_at to payroll_receipts...")
        try:
            conn.execute(text("ALTER TABLE payroll_receipts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"))
            print("  Done.")
        except Exception as e:
            print(f"  Error: {e}")

        # Optional: Add triggers for auto-updating updated_at if they don't exist
        print("Setting up auto-update triggers...")
        try:
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION update_updated_at_column()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = NOW();
                    RETURN NEW;
                END;
                $$ language 'plpgsql';
            """))

            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_receipts_updated_at') THEN
                        CREATE TRIGGER trg_receipts_updated_at
                        BEFORE UPDATE ON receipts
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column();
                    END IF;
                END $$;
            """))

            conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_payroll_receipts_updated_at') THEN
                        CREATE TRIGGER trg_payroll_receipts_updated_at
                        BEFORE UPDATE ON payroll_receipts
                        FOR EACH ROW
                        EXECUTE FUNCTION update_updated_at_column();
                    END IF;
                END $$;
            """))
            print("  Triggers set up.")
        except Exception as e:
            print(f"  Error setting up triggers: {e}")

if __name__ == "__main__":
    migrate()
