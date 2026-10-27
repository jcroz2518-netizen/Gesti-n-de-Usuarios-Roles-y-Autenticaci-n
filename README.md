# Gestión de Usuarios, Roles y Autenticación (Flask)

Módulo base de la plataforma de gestión de proyectos: autenticación completa,
control de acceso basado en roles (RBAC) y CRUD de usuarios.

## Stack

- Flask 3 · Flask-SQLAlchemy · Flask-Migrate (Alembic) · Flask-Login · Flask-WTF (CSRF) · Flask-Mail
- SQLite por defecto; MySQL/PostgreSQL cambiando `DATABASE_URL`
- Bootstrap 5 (CDN) para las vistas

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Linux/macOS: cp .env.example .env

flask db upgrade                # aplica las migraciones
flask seed                      # roles + usuarios de prueba (idempotente)
flask run                       # http://127.0.0.1:5000
```

Para usar MySQL o PostgreSQL instala el driver (`pymysql` o `psycopg`) y ajusta `DATABASE_URL` en `.env`.

## Usuarios de prueba

Contraseña de todos: `Demo1234!`

| Correo              | Rol                                 | Estado   |
|---------------------|-------------------------------------|----------|
| admin@demo.com      | Project Manager / Administrador     | Activo   |
| pm@demo.com         | Project Manager / Administrador     | Activo   |
| dev@demo.com        | Desarrollador / Miembro de Equipo   | Activo   |
| dev2@demo.com       | Desarrollador / Miembro de Equipo   | Activo   |
| cliente@demo.com    | Cliente / Stakeholder               | Activo   |
| inactivo@demo.com   | Cliente / Stakeholder               | Inactivo |

## Funcionalidades

**Autenticación** (`app/auth/`)
- Registro (crea siempre usuarios con rol *Cliente*; el Administrador asigna otros roles).
- Login con "recordarme", bloqueo de cuentas inactivas y protección contra *open redirect* en `?next=`.
- Logout por POST con token CSRF.
- Recuperación de contraseña con token firmado, caducidad configurable (`RESET_TOKEN_MAX_AGE`, 1 h por defecto)
  y de un solo uso. Si `MAIL_SERVER` está vacío, el enlace se imprime en la consola del servidor.

**RBAC** (`app/decorators.py`)
- Decorador `@role_required(*roles)`: no autenticado → login; rol no permitido → 403.
- Un usuario desactivado pierde la sesión en la siguiente petición.

| Ruta          | Administrador | Desarrollador | Cliente |
|---------------|:-------------:|:-------------:|:-------:|
| `/usuarios/`  | ✔             | ✘             | ✘       |
| `/proyectos`  | ✔             | ✘             | ✘       |
| `/tareas`     | ✔             | ✔             | ✘       |
| `/informes`   | ✔             | ✔             | ✔       |

`/proyectos`, `/tareas` e `/informes` son vistas de marcador ya protegidas, listas para los siguientes módulos.

**CRUD de usuarios** (`app/users/`, solo Administrador)
- Listado con búsqueda por nombre/correo y filtros por rol y estado.
- Alta, edición (contraseña opcional), activar/desactivar y eliminar.
- Validaciones: correo válido y único (sin distinguir mayúsculas), contraseña segura
  (≥ 8 caracteres, mayúscula, minúscula, número y carácter especial), confirmación de contraseña.
- Un administrador no puede desactivarse, eliminarse ni quitarse el rol a sí mismo.

## Tests

```bash
pytest
```

Cubren registro, login/logout, cuentas inactivas, recuperación de contraseña,
la matriz de acceso por rol y el CRUD de usuarios.

## Estructura

```
app/
  __init__.py       # create_app (factory)
  extensions.py     # db, migrate, login_manager, csrf, mail
  models.py         # Role, User
  decorators.py     # role_required
  validators.py     # contraseña segura, correo único
  seeds.py          # comando `flask seed`
  auth/             # registro, login, logout, recuperación
  users/            # CRUD de usuarios
  main/             # panel y vistas por rol
  templates/
migrations/         # migraciones Alembic
tests/
config.py
run.py
```
