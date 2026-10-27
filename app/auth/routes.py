from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import Role, User
from .email import send_reset_email
from .forms import ForgotPasswordForm, LoginForm, RegisterForm, ResetPasswordForm

bp = Blueprint("auth", __name__)


def _find_by_email(email):
    return db.session.scalar(db.select(User).where(db.func.lower(User.email) == email.strip().lower()))


@bp.route("/registro", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegisterForm()
    if form.validate_on_submit():
        # El registro público siempre crea Clientes; el Administrador asigna otros roles.
        client_role = db.session.scalar(db.select(Role).filter_by(name=Role.CLIENT))
        user = User(full_name=form.full_name.data.strip(), email=form.email.data.strip().lower(), role=client_role)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = _find_by_email(form.email.data)
        if user is None or not user.check_password(form.password.data):
            flash("Correo o contraseña incorrectos.", "danger")
        elif not user.is_active:
            flash("Tu cuenta está inactiva. Contacta con un administrador.", "warning")
        else:
            login_user(user, remember=form.remember.data)
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            next_page = request.args.get("next")
            # Solo se aceptan rutas relativas para evitar open redirects.
            if not next_page or urlsplit(next_page).netloc or not next_page.startswith("/"):
                next_page = url_for("main.dashboard")
            return redirect(next_page)
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/recuperar", methods=["GET", "POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = _find_by_email(form.email.data)
        if user and user.is_active:
            send_reset_email(user)
        # Mismo mensaje exista o no el correo, para no revelar cuentas.
        flash("Si el correo está registrado, recibirás un enlace para restablecer la contraseña.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@bp.route("/restablecer/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = User.verify_reset_token(token)
    if user is None:
        flash("El enlace no es válido o ha caducado.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form)
