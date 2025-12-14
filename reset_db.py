from src.infrastructure.database.models import Base, db, User
from src.infrastructure.auth import AuthService

def reset_database():
    print("⚠️  DANGER: Dropping all tables...")
    Base.metadata.drop_all(db.engine)
    
    print("Creating new schema...")
    Base.metadata.create_all(db.engine)
    
    print("Creating Default Admin...")
    auth = AuthService()
    admin = auth.create_user("admin", "admin123", role="ADMIN", config={"capital": 100000})
    
    if admin:
        print(f"✅ User 'admin' created with password 'admin123'")
    else:
        print("❌ Failed to create admin.")

if __name__ == "__main__":
    permission = input("Type 'DELETE' to confirm wiping the database: ")
    if permission == "DELETE":
        reset_database()
    else:
        print("Aborted.")
