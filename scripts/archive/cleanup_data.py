from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
Session = sessionmaker(bind=engine)
db = Session()

def data_clean_up():
    print("--- Starting Data Cleanup ---")
    
    # IDs confirmed:
    REAL_ORG = 'ba39ac75-af1e-4334-9389-c7331ced43e5'
    EMPTY_ORG = 'bc0b5009-3764-4999-89c4-bc45e864dcfe'
    ADMIN_EMAIL = 'scandrolifacundo2012@gmail.com'
    
    # 1. Rename the empty one
    print(f"Renaming empty org {EMPTY_ORG}...")
    db.execute(text("UPDATE organizations SET name = 'TEST SRL (OLD/EMPTY)', slug = 'test-srl-old' WHERE id = :id"), {"id": EMPTY_ORG})
    
    # 2. Move the admin
    print(f"Moving admin {ADMIN_EMAIL} to org {REAL_ORG}...")
    db.execute(text("UPDATE users SET organization_id = :real WHERE email = :email"), {"real": REAL_ORG, "email": ADMIN_EMAIL})
    
    db.commit()
    print("--- Cleanup Finished ---")

if __name__ == "__main__":
    data_clean_up()
