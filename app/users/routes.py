from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from ..decorators import role_required
from ..extensions import db
from ..models import Role, User
from .forms import DeleteForm, UserForm

bp = Blueprint("users", __name__)


def _get_user_or_404(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    return user


@bp.route("/")
@role_required(Role.ADMIN)
def index():
    q = request.args.get("q", "").strip()
    role = request.args.get("rol", "")
    status = request.args.get("estado", "")

    query = db.select(User).join(Role).order_by(User.id)
    if q:
        like = f"%{q}%"
        query = query.where(db.or_(User.full_name.ilike(like), User.email.ilike(like)))
    if role:
        query = query.where(Role.name == role)
    if status in ("activo", "inactivo"):
        query = query.where(User.active.is_(status == "activo"))

    users = db.session.scalars(query).all()
    roles = db.session.scalars(db.select(Role).order_by(Role.id)).all()
    return render_template("users/index.html", users=users, roles=roles, action_form=DeleteForm())


@bp.route("/nuevo", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def create():
    form = UserForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data.strip(),
            email=form.email.data.strip().lower(),
            role_id=form.role_id.data,
            active=form.active.data,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(f"Usuario {user.email} creado.", "success")
        return redirect(url_for("users.index"))
    return render_template("users/form.html", form=form, title="Nuevo usuario")


@bp.route("/<int:user_id>/editar", methods=["GET", "POST"])
@role_required(Role.ADMIN)
def edit(user_id):
    user = _get_user_or_404(user_id)
    form = UserForm(obj=user, user=user)
    if form.validate_on_submit():
        if user.id == current_user.id and (not form.active.data or form.role_id.data != user.role_id):
            flash("No puedes desactivarte ni quitarte el rol de administrador a ti mismo.", "danger")
            return render_template("users/form.html", form=form, title="Editar usuario", user=user)
        user.full_name = form.full_name.data.strip()
        user.email = form.email.data.strip().lower()
        user.role_id = form.role_id.data
        user.active = form.active.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash("Usuario actualizado.", "success")
        return redirect(url_for("users.index"))
    return render_template("users/form.html", form=form, title="Editar usuario", user=user)


@bp.route("/<int:user_id>/estado", methods=["POST"])
@role_required(Role.ADMIN)
def toggle_active(user_id):
    user = _get_user_or_404(user_id)
    if not DeleteForm().validate_on_submit():
        abort(400)
    if user.id == current_user.id:
        flash("No puedes desactivar tu propia cuenta.", "danger")
    else:
        user.active = not user.active
        db.session.commit()
        flash(f"Usuario {'activado' if user.active else 'desactivado'}.", "success")
    return redirect(url_for("users.index"))


@bp.route("/<int:user_id>/eliminar", methods=["POST"])
@role_required(Role.ADMIN)
def delete(user_id):
    user = _get_user_or_404(user_id)
    if not DeleteForm().validate_on_submit():
        abort(400)
    if user.id == current_user.id:
        flash("No puedes eliminar tu propia cuenta.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash("Usuario eliminado.", "success")
    return redirect(url_for("users.index"))
