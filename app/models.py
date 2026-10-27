from datetime import datetime, timezone

from flask import current_app
from flask_login import UserMixin
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, login_manager


class Role(db.Model):
    __tablename__ = "roles"

    ADMIN = "admin"
    DEVELOPER = "developer"
    CLIENT = "client"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True, nullable=False)
    label = db.Column(db.String(60), nullable=False)
    description = db.Column(db.String(255))

    users = db.relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role {self.name}>"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    role = db.relationship("Role", back_populates="users")

    # Flask-Login rechaza el login de usuarios con is_active == False
    @property
    def is_active(self):
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, *names):
        return self.role is not None and self.role.name in names

    # --- Recuperación de contraseña ---------------------------------------
    @staticmethod
    def _serializer():
        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")

    def get_reset_token(self):
        # Incluye parte del hash actual: el token deja de valer en cuanto
        # la contraseña cambia (uso único).
        return self._serializer().dumps({"uid": self.id, "h": self.password_hash[-12:]})

    @classmethod
    def verify_reset_token(cls, token):
        max_age = current_app.config["RESET_TOKEN_MAX_AGE"]
        try:
            data = cls._serializer().loads(token, max_age=max_age)
        except (SignatureExpired, BadSignature):
            return None
        user = db.session.get(cls, data.get("uid"))
        if user is None or user.password_hash[-12:] != data.get("h"):
            return None
        return user

    def __repr__(self):
        return f"<User {self.email}>"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
