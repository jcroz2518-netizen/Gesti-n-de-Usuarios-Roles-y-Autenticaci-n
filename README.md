# Gestión de Usuarios, Roles y Autenticación (Flask)

Plataforma de gestión de proyectos de software.

- **Hito 1** — autenticación completa, control de acceso basado en roles (RBAC) y CRUD de usuarios.
- **Hito 2** — CRUD de proyectos, asignación de miembros con su rol en el proyecto y
  Estructura de Desglose de Trabajo (EDT/WBS) básica por fases o hitos.

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

python base_datos.py      # crea las tablas (migraciones) y carga usuarios y proyectos de prueba
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

Proyectos de prueba: **Portal de clientes** (activo, 4 miembros, 5 fases) y
**App móvil de inventario** (en planificación, 2 miembros, 1 fase). Solo se cargan si no hay
ningún proyecto en la base de datos.

## Base de datos y migraciones

En `base_datos.py`, la lista `MIGRACIONES` contiene scripts SQL. La versión aplicada se
guarda en `PRAGMA user_version`, así cada script se ejecuta una sola vez. Para cambiar el
esquema se **añade** un script nuevo al final de la lista; al arrancar `pagina.py` se
aplican las migraciones pendientes.

| Migración | Tablas |
|-----------|--------|
| 1 | `roles` (id, nombre, etiqueta, descripcion) y `usuarios` (id, nombre, correo único, contrasena con hash, activo, rol_id, creado, ultimo_acceso) |
| 2 | `proyectos` (id, nombre, descripcion, objetivos, fecha_inicio, fecha_fin, presupuesto, estado, creado), `miembros_proyecto` (proyecto_id, usuario_id, rol_proyecto, asignado) y `fases` (id, proyecto_id, nombre, descripcion, orden, fecha_inicio, fecha_fin, estado) |

Al borrar un proyecto se borran sus miembros y fases, y al borrar un usuario se le quita de
todos los equipos (`ON DELETE CASCADE`).

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

`/tareas` e `/informes` son páginas provisionales ya protegidas, listas para los siguientes módulos.

**CRUD de usuarios** (solo Administrador)
- Listado con búsqueda por nombre/correo y filtros por rol y estado.
- Alta, edición (contraseña opcional), activar/desactivar y eliminar.
- Validaciones (`validaciones.py`): correo válido y único (sin distinguir mayúsculas),
  contraseña segura (≥ 8 caracteres, mayúscula, minúscula, número y carácter especial)
  y confirmación de contraseña.
- Un administrador no puede desactivarse, eliminarse ni quitarse el rol a sí mismo.

**Proyectos** (solo Administrador)
- Listado con búsqueda por nombre/descripción y filtro por estado; muestra presupuesto,
  tamaño del equipo y fases completadas.
- Alta, edición, detalle y eliminación. Campos: nombre, descripción, objetivos, fecha de
  inicio, fecha de fin estimada, presupuesto base y estado
  (*En planificación*, *Activo*, *Pausado*, *Finalizado*).
- Validaciones: fechas válidas y fin ≥ inicio, presupuesto numérico ≥ 0, estado válido, y al
  editar no se pueden cambiar las fechas si dejarían fases fuera del proyecto.

**Equipo del proyecto**
- En el detalle del proyecto se añaden usuarios activos y se elige su rol específico en el
  desarrollo (Project Manager, Líder técnico, Analista, Desarrollador backend/frontend, QA,
  DevOps, Stakeholder...; lista `ROLES_PROYECTO` en `base_datos.py`).
- Se puede cambiar el rol de un miembro o retirarlo del equipo.

**Fases / EDT**
- Cada proyecto se divide en fases o hitos con nombre, descripción/entregables, orden,
  fechas y estado (*Pendiente*, *En curso*, *Completada*).
- Las fechas de una fase deben estar dentro de las del proyecto.
- El detalle muestra el avance del proyecto según las fases completadas.

| Ruta                                              | Acción                          |
|---------------------------------------------------|---------------------------------|
| `GET /proyectos`                                  | Listado y filtros               |
| `GET/POST /proyectos/nuevo`                       | Crear proyecto                  |
| `GET /proyectos/<id>`                             | Detalle, equipo y fases         |
| `GET/POST /proyectos/<id>/editar`                 | Editar proyecto                 |
| `POST /proyectos/<id>/eliminar`                   | Eliminar proyecto               |
| `POST /proyectos/<id>/miembros`                   | Añadir miembro o cambiar su rol |
| `POST /proyectos/<id>/miembros/<usuario>/quitar`  | Retirar miembro                 |
| `GET/POST /proyectos/<id>/fases/nueva`            | Crear fase                      |
| `GET/POST /proyectos/<id>/fases/<fase>/editar`    | Editar fase                     |
| `POST /proyectos/<id>/fases/<fase>/eliminar`      | Eliminar fase                   |

## Pruebas

```bash
pytest
```

Cubren migraciones y seeders, registro, login/logout, cuentas inactivas, recuperación de
contraseña, CSRF, la matriz de acceso por rol, el CRUD de usuarios y, del Hito 2, el CRUD de
proyectos, la asignación de miembros y las fases.

## Variables de entorno opcionales

| Variable      | Para qué                                   | Por defecto              |
|---------------|--------------------------------------------|--------------------------|
| `SECRET_KEY`  | Firma de la sesión y de los enlaces        | `dev-insegura-cambiar`   |
| `BASE_DATOS`  | Ruta del archivo SQLite                    | `usuarios.db`            |
