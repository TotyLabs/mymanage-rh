import subprocess
from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found in .env")
    exit(1)

# we can use psql to check the table
subprocess.run(["psql", db_url, "-c", "\\d signature_events"])
