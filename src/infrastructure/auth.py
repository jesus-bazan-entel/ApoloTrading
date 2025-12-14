import bcrypt
from sqlalchemy.orm import Session
from src.infrastructure.database.models import User, db

class AuthService:
    def __init__(self, session: Session = None):
        self.session = session or db.get_session()

    def hash_password(self, password: str) -> str:
        """Hash a password for storing."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a stored password against one provided by user."""
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

    def create_user(self, username, password, role="USER", config=None):
        if self.get_user_by_username(username):
            return None # User exists
        
        hashed = self.hash_password(password)
        new_user = User(
            username=username,
            password_hash=hashed,
            role=role,
            config=config or {}
        )
        self.session.add(new_user)
        self.session.commit()
        return new_user

    def get_user_by_username(self, username):
        return self.session.query(User).filter_by(username=username).first()

    def login(self, username, password):
        user = self.get_user_by_username(username)
        if user and self.verify_password(password, user.password_hash):
            return user
        return None
