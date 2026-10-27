from flask import current_app, url_for
from flask_mail import Message

from ..extensions import mail


def send_reset_email(user):
    token = user.get_reset_token()
    link = url_for("auth.reset_password", token=token, _external=True)
    body = (
        f"Hola {user.full_name},\n\n"
        f"Para restablecer tu contraseña entra en:\n{link}\n\n"
        "Si no solicitaste el cambio, ignora este correo."
    )

    if not current_app.config.get("MAIL_SERVER"):
        # Sin SMTP configurado (desarrollo): el enlace se muestra en la consola.
        current_app.logger.warning("Enlace de recuperación para %s: %s", user.email, link)
        return link

    mail.send(Message("Recuperación de contraseña", recipients=[user.email], body=body))
    return link
