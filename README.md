# Gestión de Usuarios, Roles y Autenticación (Flask)

Módulo base de la plataforma de gestión de proyectos: autenticación completa,
control de acceso basado en roles (RBAC) y CRUD de usuarios.
Hecho solo con **Flask** y **sqlite3** (sin librerías extra).

## Estructura

```
pagina.py         # aplicación Flask: rutas, sesión, decoradores de rol, recuperación de contraseña
base_datos.py     # conexión sqlite3, migraciones, datos de prueba y consultas SQL
validaciones.py   # validaciones de formularios (correo, contraseña segura, campos)
static/           # estilos.css
templates/        # plantillas HTML (Bootstrap 5 por CDN)
usuarios.db       # base de datos (se crea sola)
test_pagina.py    # pruebas automáticas
```

## Puesta en marcha

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python base_datos.py      # crea las tablas (migraciones) y carga los datos de prueba
python pagina.py          # http://127.0.0.1:5000
```

`python base_datos.py --reiniciar` borra la base de datos y la vuelve a crear desde cero.

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

## Base de datos y migraciones

En `base_datos.py`, la lista `MIGRACIONES` contiene scripts SQL. La versión aplicada se
guarda en `PRAGMA user_version`, así cada script se ejecuta una sola vez. Para cambiar el
esquema (por ejemplo, añadir la tabla de proyectos) se **añade** un script nuevo al final
de la lista; al arrancar `pagina.py` se aplican las migraciones pendientes.

Tablas: `roles` (id, nombre, etiqueta, descripcion) y `usuarios` (id, nombre, correo único,
contrasena con hash, activo, rol_id, creado, ultimo_acceso).

## Funcionalidades

**Autenticación**
- Registro: crea siempre usuarios con rol *Cliente*; el Administrador asigna otros roles.
- Login con "Recordarme", bloqueo de cuentas inactivas y protección contra redirecciones externas en `?next=`.
- Logout.
- Recuperación de contraseña con enlace firmado que caduca en 1 hora y solo sirve una vez.
  Sin SMTP configurado, el enlace se imprime en la consola donde corre `pagina.py`.
  Para enviarlo por correo, define las variables `SMTP_SERVIDOR`, `SMTP_PUERTO`,
  `SMTP_USUARIO`, `SMTP_CONTRASENA` (y opcionalmente `SMTP_REMITENTE`).
- Todos los formularios POST llevan token CSRF.

**Roles** — decoradores en `pagina.py`:
- `@login_requerido`: sin sesión → redirige al login.
- `@rol_requerido(ADMIN, ...)`: rol no permitido → error 403.
- Un usuario desactivado pierde la sesión en la siguiente petición.

| Ruta          | Administrador | Desarrollador | Cliente |
|---------------|:-------------:|:-------------:|:-------:|
| `/usuarios`   | ✔             | ✘             | ✘       |
| `/proyectos`  | ✔             | ✘             | ✘       |
| `/tareas`     | ✔             | ✔             | ✘       |
| `/informes`   | ✔             | ✔             | ✔       |

`/proyectos`, `/tareas` e `/informes` son páginas provisionales ya protegidas, listas para los siguientes módulos.

**CRUD de usuarios** (solo Administrador)
- Listado con búsqueda por nombre/correo y filtros por rol y estado.
- Alta, edición (contraseña opcional), activar/desactivar y eliminar.
- Validaciones (`validaciones.py`): correo válido y único (sin distinguir mayúsculas),
  contraseña segura (≥ 8 caracteres, mayúscula, minúscula, número y carácter especial)
  y confirmación de contraseña.
- Un administrador no puede desactivarse, eliminarse ni quitarse el rol a sí mismo.

## Pruebas

```bash
pytest
```

Cubren migraciones y seeders, registro, login/logout, cuentas inactivas, recuperación de
contraseña, CSRF, la matriz de acceso por rol y el CRUD de usuarios.

## Variables de entorno opcionales

| Variable      | Para qué                                   | Por defecto              |
|---------------|--------------------------------------------|--------------------------|
| `SECRET_KEY`  | Firma de la sesión y de los enlaces        | `dev-insegura-cambiar`   |
| `BASE_DATOS`  | Ruta del archivo SQLite                    | `usuarios.db`            |
