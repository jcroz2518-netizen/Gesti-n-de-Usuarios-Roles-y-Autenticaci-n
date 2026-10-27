import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insegura-cambiar")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///gestion.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Recuperación de contraseña
    RESET_TOKEN_MAX_AGE = int(os.getenv("RESET_TOKEN_MAX_AGE", 3600))  # segundos

    # Correo (opcional)
    MAIL_SERVER = os.getenv("MAIL_SERVER") or None
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "1") == "1"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-reply@gestion.local")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    MAIL_SERVER = None
