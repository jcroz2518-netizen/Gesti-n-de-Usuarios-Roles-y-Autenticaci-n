from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def role_required(*roles):
    """Restringe una vista a usuarios autenticados con alguno de los roles dados.

    No autenticado -> redirige al login.
    Rol no permitido -> 403.
    """

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not current_user.has_role(*roles):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
