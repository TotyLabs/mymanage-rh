import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    print("----- ALEMBIC VERSION -----")
    for row in conn.execute(text("SELECT version_num FROM alembic_version")):
        print(row[0])
