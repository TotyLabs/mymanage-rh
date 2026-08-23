import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

confirm = input("Are you sure you want to drop 'webhook_outbox'? (y/N): ")
if confirm.lower() != 'y':
    print("Aborted.")
    exit(0)

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    print("----- DROPPING TABLE STRAGGLER -----")
    conn.execute(text("DROP TABLE IF EXISTS webhook_outbox CASCADE"))
    conn.commit()
    print("Done.")
