from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
from models.tables import Notification, User

load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
Session = sessionmaker(bind=engine)
db = Session()

def test_query():
    org_id = 'ba39ac75-af1e-4334-9389-c7331ced43e5' # From debug output
    
    # Try the exact same query as the API
    notifs = db.query(Notification, User.email, User.full_name).join(
        User, Notification.sender_user_id == User.id
    ).filter(
        Notification.company_id == org_id
    ).order_by(Notification.created_at.desc()).all()
    
    print(f"Found {len(notifs)} notifications for org {org_id}")
    for n, email, name in notifs:
        print(f"ID: {n.id}, Sender: {name} ({email}), Msg: {n.message}")

if __name__ == "__main__":
    test_query()
