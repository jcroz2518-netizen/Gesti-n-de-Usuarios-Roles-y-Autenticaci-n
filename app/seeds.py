import click

from .extensions import db
from .models import Role, User

ROLES = [
    (Role.ADMIN, "Project Manager / Administrador", "Gestiona proyectos, asigna presupuestos y miembros."),
    (Role.DEVELOPER, "Desarrollador / Miembro de Equipo", "Gestiona tareas y reporta horas/avances."),
    (Role.CLIENT, "Cliente / Stakeholder", "Solo visualiza informes, métricas y estado del proyecto."),
]

# Contraseña común de los datos de prueba (cumple la política de contraseñas).
DEMO_PASSWORD = "Demo1234!"

USERS = [
    ("Ana Administradora", "admin@demo.com", Role.ADMIN, True),
    ("Pedro Manager", "pm@demo.com", Role.ADMIN, True),
    ("Diego Desarrollador", "dev@demo.com", Role.DEVELOPER, True),
    ("Lucía Programadora", "dev2@demo.com", Role.DEVELOPER, True),
    ("Carla Cliente", "cliente@demo.com", Role.CLIENT, True),
    ("Iván Inactivo", "inactivo@demo.com", Role.CLIENT, False),
]


def seed_roles():
    for name, label, description in ROLES:
        role = db.session.scalar(db.select(Role).filter_by(name=name))
        if role is None:
            db.session.add(Role(name=name, label=label, description=description))
        else:
            role.label, role.description = label, description
    db.session.commit()


def seed_users():
    roles = {r.name: r for r in db.session.scalars(db.select(Role))}
    created = 0
    for full_name, email, role_name, active in USERS:
        if db.session.scalar(db.select(User).filter_by(email=email)):
            continue
        user = User(full_name=full_name, email=email, role=roles[role_name], active=active)
        user.set_password(DEMO_PASSWORD)
        db.session.add(user)
        created += 1
    db.session.commit()
    return created


def register_commands(app):
    @app.cli.command("seed")
    @click.option("--sin-usuarios", is_flag=True, help="Crea solo los roles.")
    def seed(sin_usuarios):
        """Carga roles y usuarios de prueba (idempotente)."""
        seed_roles()
        click.echo("Roles cargados.")
        if not sin_usuarios:
            n = seed_users()
            click.echo(f"{n} usuarios de prueba creados (contraseña: {DEMO_PASSWORD}).")
