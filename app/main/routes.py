from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from ..decorators import role_required
from ..models import Role

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/panel")
@login_required
def dashboard():
    return render_template("main/dashboard.html")


# Las siguientes vistas son de demostración del RBAC; los módulos reales
# de proyectos, tareas e informes se construirán sobre ellas.

@bp.route("/proyectos")
@role_required(Role.ADMIN)
def projects():
    return render_template(
        "main/section.html",
        title="Proyectos",
        text="Gestión de proyectos, presupuestos y asignación de miembros.",
    )


@bp.route("/tareas")
@role_required(Role.ADMIN, Role.DEVELOPER)
def tasks():
    return render_template(
        "main/section.html",
        title="Tareas",
        text="Gestión de tareas y registro de horas y avances.",
    )


@bp.route("/informes")
@role_required(Role.ADMIN, Role.DEVELOPER, Role.CLIENT)
def reports():
    return render_template(
        "main/section.html",
        title="Informes",
        text="Informes, métricas y estado de los proyectos (solo lectura para clientes).",
    )
