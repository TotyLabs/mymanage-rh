import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    print("----- WEBHOOK OUTBOX ROWS -----")
    for row in conn.execute(text("SELECT count(*) FROM webhook_outbox")):
        print(row[0])
