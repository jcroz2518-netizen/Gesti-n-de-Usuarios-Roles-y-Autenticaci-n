import re

from wtforms.validators import ValidationError

from .extensions import db
from .models import User

PASSWORD_RULES = (
    (r".{8,}", "al menos 8 caracteres"),
    (r"[A-Z]", "una mayúscula"),
    (r"[a-z]", "una minúscula"),
    (r"\d", "un número"),
    (r"[^A-Za-z0-9]", "un carácter especial"),
)


def strong_password(_form, field):
    if not field.data:
        return
    missing = [msg for pattern, msg in PASSWORD_RULES if not re.search(pattern, field.data)]
    if missing:
        raise ValidationError("La contraseña debe tener " + ", ".join(missing) + ".")


def unique_email(exclude_user_id=None):
    def _check(_form, field):
        query = db.select(User).where(db.func.lower(User.email) == field.data.strip().lower())
        if exclude_user_id is not None:
            query = query.where(User.id != exclude_user_id)
        if db.session.scalar(query):
            raise ValidationError("Ya existe un usuario con ese correo.")

    return _check
