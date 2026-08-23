import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Import models
from models.tables import User, Employee, PayrollReceipt, SignatureRequest

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
Session = sessionmaker(bind=engine)

def test_db():
    print("Testing DB mapped classes...")
    with Session() as session:
        # Check if we can query the main tables without UndefinedColumn errors
        users = session.query(User).limit(1).all()
        print(f"Users found: {len(users)}")
        
        employees = session.query(Employee).limit(1).all()
        print(f"Employees found: {len(employees)}")
        
        receipts = session.query(PayrollReceipt).limit(1).all()
        print(f"Receipts found: {len(receipts)}")
        
        sigs = session.query(SignatureRequest).limit(1).all()
        print(f"SignatureRequests found: {len(sigs)}")
        
    print("SUCCESS: All models query correctly!")

if __name__ == "__main__":
    test_db()
