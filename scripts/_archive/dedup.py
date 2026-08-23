import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    print("----- DEDUPLICATING PAYROLL BATCHES -----")
    # Keep the batch with the max uploaded_at, delete others
    dedup_sql = """
    DELETE FROM payroll_batches a USING (
      SELECT MIN(ctid) as ctid, organization_id, source_pdf_sha256
      FROM payroll_batches 
      GROUP BY organization_id, source_pdf_sha256 HAVING COUNT(*) > 1
    ) b
    WHERE a.organization_id = b.organization_id 
      AND a.source_pdf_sha256 = b.source_pdf_sha256 
      AND a.ctid <> b.ctid
    """
    
    # Run in a loop until no more duplicates (in case there are >2 copies)
    while True:
        res = conn.execute(text(dedup_sql))
        conn.commit()
        if res.rowcount == 0:
            break
        print(f"Deleted {res.rowcount} duplicate rows.")
    
    print("Done deduplicating.")
