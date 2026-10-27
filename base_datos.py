"""Conexión a SQLite, migraciones, datos de prueba (seeders) y consultas.

Uso desde la terminal:
    python base_datos.py            -> aplica migraciones y carga datos de prueba
    python base_datos.py --reiniciar -> borra la base de datos y la vuelve a crear
"""
import os
import sqlite3
import sys

from flask import current_app, g
from werkzeug.security import generate_password_hash

CARPETA = os.path.dirname(os.path.abspath(__file__))
RUTA_BD = os.environ.get("BASE_DATOS", os.path.join(CARPETA, "usuarios.db"))

ADMIN = "admin"
DESARROLLADOR = "desarrollador"
CLIENTE = "cliente"

# ---------------------------------------------------------------------------
# Migraciones
# Cada elemento es un script SQL. La versión aplicada se guarda en
# PRAGMA user_version, así cada migración se ejecuta una sola vez.
# Para cambiar el esquema se AÑADE un script nuevo al final, nunca se edita uno viejo.
# ---------------------------------------------------------------------------
MIGRACIONES = [
    # 1 - tablas de roles y usuarios
    """
    CREATE TABLE roles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre      TEXT NOT NULL UNIQUE,
        etiqueta    TEXT NOT NULL,
        descripcion TEXT
    );

    CREATE TABLE usuarios (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre        TEXT NOT NULL,
        correo        TEXT NOT NULL UNIQUE COLLATE NOCASE,
        contrasena    TEXT NOT NULL,
        activo        INTEGER NOT NULL DEFAULT 1,
        rol_id        INTEGER NOT NULL REFERENCES roles(id),
        creado        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        ultimo_acceso TEXT
    );

    INSERT INTO roles (nombre, etiqueta, descripcion) VALUES
        ('admin', 'Project Manager / Administrador', 'Gestiona proyectos, asigna presupuestos y miembros.'),
        ('desarrollador', 'Desarrollador / Miembro de Equipo', 'Gestiona tareas y reporta horas/avances.'),
        ('cliente', 'Cliente / Stakeholder', 'Solo visualiza informes, métricas y estado del proyecto.');
    """,
]

# ---------------------------------------------------------------------------
# Datos de prueba
# ---------------------------------------------------------------------------
CONTRASENA_PRUEBA = "Demo1234!"

USUARIOS_PRUEBA = [
    ("Ana Administradora", "admin@demo.com", ADMIN, 1),
    ("Pedro Manager", "pm@demo.com", ADMIN, 1),
    ("Diego Desarrollador", "dev@demo.com", DESARROLLADOR, 1),
    ("Lucía Programadora", "dev2@demo.com", DESARROLLADOR, 1),
    ("Carla Cliente", "cliente@demo.com", CLIENTE, 1),
    ("Iván Inactivo", "inactivo@demo.com", CLIENTE, 0),
]


def abrir(ruta):
    conexion = sqlite3.connect(ruta)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def migrar(conexion):
    version = conexion.execute("PRAGMA user_version").fetchone()[0]
    for numero, script in enumerate(MIGRACIONES[version:], start=version + 1):
        conexion.executescript(script)
        conexion.execute(f"PRAGMA user_version = {numero}")
        conexion.commit()
        print(f"Migración {numero} aplicada.")


def sembrar(conexion):
    creados = 0
    for nombre, correo, rol, activo in USUARIOS_PRUEBA:
        if conexion.execute("SELECT 1 FROM usuarios WHERE correo = ?", (correo,)).fetchone():
            continue
        conexion.execute(
            "INSERT INTO usuarios (nombre, correo, contrasena, activo, rol_id) "
            "VALUES (?, ?, ?, ?, (SELECT id FROM roles WHERE nombre = ?))",
            (nombre, correo, generate_password_hash(CONTRASENA_PRUEBA), activo, rol),
        )
        creados += 1
    conexion.commit()
    return creados


def inicializar(ruta=RUTA_BD, con_datos=False):
    conexion = abrir(ruta)
    migrar(conexion)
    if con_datos:
        sembrar(conexion)
    conexion.close()


# ---------------------------------------------------------------------------
# Conexión por petición (una por request, se cierra al terminar)
# ---------------------------------------------------------------------------
def obtener_conexion():
    if "bd" not in g:
        g.bd = abrir(current_app.config["BASE_DATOS"])
    return g.bd


def cerrar_conexion(_error=None):
    conexion = g.pop("bd", None)
    if conexion is not None:
        conexion.close()


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
CONSULTA_USUARIO = """
    SELECT u.*, r.nombre AS rol, r.etiqueta AS rol_etiqueta, r.descripcion AS rol_descripcion
    FROM usuarios u JOIN roles r ON r.id = u.rol_id
"""


def listar_roles():
    return obtener_conexion().execute("SELECT * FROM roles ORDER BY id").fetchall()


def obtener_usuario(usuario_id):
    return obtener_conexion().execute(CONSULTA_USUARIO + " WHERE u.id = ?", (usuario_id,)).fetchone()


def buscar_usuario_por_correo(correo):
    return obtener_conexion().execute(CONSULTA_USUARIO + " WHERE u.correo = ?", (correo.strip(),)).fetchone()


def correo_existe(correo, excluir_id=None):
    fila = obtener_conexion().execute(
        "SELECT 1 FROM usuarios WHERE correo = ? AND id != ?", (correo.strip(), excluir_id or 0)
    ).fetchone()
    return fila is not None


def listar_usuarios(texto="", rol="", estado=""):
    sql = CONSULTA_USUARIO + " WHERE 1 = 1"
    parametros = []
    if texto:
        sql += " AND (u.nombre LIKE ? OR u.correo LIKE ?)"
        parametros += [f"%{texto}%", f"%{texto}%"]
    if rol:
        sql += " AND r.nombre = ?"
        parametros.append(rol)
    if estado in ("activo", "inactivo"):
        sql += " AND u.activo = ?"
        parametros.append(1 if estado == "activo" else 0)
    return obtener_conexion().execute(sql + " ORDER BY u.id", parametros).fetchall()


def crear_usuario(nombre, correo, contrasena, rol_id, activo=True):
    conexion = obtener_conexion()
    cursor = conexion.execute(
        "INSERT INTO usuarios (nombre, correo, contrasena, rol_id, activo) VALUES (?, ?, ?, ?, ?)",
        (nombre.strip(), correo.strip().lower(), generate_password_hash(contrasena), rol_id, int(activo)),
    )
    conexion.commit()
    return cursor.lastrowid


def actualizar_usuario(usuario_id, nombre, correo, rol_id, activo):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE usuarios SET nombre = ?, correo = ?, rol_id = ?, activo = ? WHERE id = ?",
        (nombre.strip(), correo.strip().lower(), rol_id, int(activo), usuario_id),
    )
    conexion.commit()


def cambiar_contrasena(usuario_id, contrasena):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE usuarios SET contrasena = ? WHERE id = ?", (generate_password_hash(contrasena), usuario_id)
    )
    conexion.commit()


def cambiar_estado(usuario_id):
    conexion = obtener_conexion()
    conexion.execute("UPDATE usuarios SET activo = 1 - activo WHERE id = ?", (usuario_id,))
    conexion.commit()


def eliminar_usuario(usuario_id):
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conexion.commit()


def registrar_acceso(usuario_id):
    conexion = obtener_conexion()
    conexion.execute("UPDATE usuarios SET ultimo_acceso = CURRENT_TIMESTAMP WHERE id = ?", (usuario_id,))
    conexion.commit()


if __name__ == "__main__":
    if "--reiniciar" in sys.argv and os.path.exists(RUTA_BD):
        os.remove(RUTA_BD)
        print("Base de datos eliminada.")
    conexion = abrir(RUTA_BD)
    migrar(conexion)
    print(f"{sembrar(conexion)} usuarios de prueba creados (contraseña: {CONTRASENA_PRUEBA}).")
    conexion.close()
