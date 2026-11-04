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
    # 2 - proyectos, miembros del equipo y fases (EDT/WBS)
    """
    CREATE TABLE proyectos (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre       TEXT NOT NULL,
        descripcion  TEXT NOT NULL DEFAULT '',
        objetivos    TEXT NOT NULL DEFAULT '',
        fecha_inicio TEXT NOT NULL,
        fecha_fin    TEXT NOT NULL,
        presupuesto  REAL NOT NULL DEFAULT 0 CHECK (presupuesto >= 0),
        estado       TEXT NOT NULL DEFAULT 'planificacion'
                     CHECK (estado IN ('planificacion', 'activo', 'pausado', 'finalizado')),
        creado       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE miembros_proyecto (
        proyecto_id  INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        usuario_id   INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        rol_proyecto TEXT NOT NULL,
        asignado     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (proyecto_id, usuario_id)
    );

    CREATE TABLE fases (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        proyecto_id  INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
        nombre       TEXT NOT NULL,
        descripcion  TEXT NOT NULL DEFAULT '',
        orden        INTEGER NOT NULL DEFAULT 1,
        fecha_inicio TEXT NOT NULL,
        fecha_fin    TEXT NOT NULL,
        estado       TEXT NOT NULL DEFAULT 'pendiente'
                     CHECK (estado IN ('pendiente', 'en_curso', 'completada'))
    );

    CREATE INDEX idx_fases_proyecto ON fases (proyecto_id, orden);
    """,
]

ESTADOS_PROYECTO = {
    "planificacion": "En planificación",
    "activo": "Activo",
    "pausado": "Pausado",
    "finalizado": "Finalizado",
}

ESTADOS_FASE = {
    "pendiente": "Pendiente",
    "en_curso": "En curso",
    "completada": "Completada",
}

# Rol específico de cada miembro dentro del desarrollo de un proyecto
ROLES_PROYECTO = [
    "Project Manager",
    "Líder técnico",
    "Analista",
    "Arquitecto de software",
    "Desarrollador backend",
    "Desarrollador frontend",
    "Desarrollador full stack",
    "Diseñador UX/UI",
    "QA / Tester",
    "DevOps",
    "Stakeholder",
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

# (nombre, descripción, objetivos, inicio, fin, presupuesto, estado, miembros, fases)
PROYECTOS_PRUEBA = [
    (
        "Portal de clientes",
        "Portal web para que los clientes consulten pedidos, facturas e incidencias.",
        "Reducir un 40 % las llamadas al soporte y centralizar la atención al cliente.",
        "2026-09-01", "2027-02-26", 85000, "activo",
        [("pm@demo.com", "Project Manager"), ("dev@demo.com", "Desarrollador backend"),
         ("dev2@demo.com", "Desarrollador frontend"), ("cliente@demo.com", "Stakeholder")],
        [("Análisis de requisitos", "2026-09-01", "2026-09-30", "completada"),
         ("Diseño", "2026-10-01", "2026-10-31", "completada"),
         ("Desarrollo", "2026-11-02", "2027-01-15", "en_curso"),
         ("Pruebas", "2027-01-18", "2027-02-12", "pendiente"),
         ("Despliegue", "2027-02-15", "2027-02-26", "pendiente")],
    ),
    (
        "App móvil de inventario",
        "Aplicación móvil para registrar entradas y salidas de almacén con lector de códigos.",
        "Eliminar el inventario en papel y tener el stock actualizado en tiempo real.",
        "2027-01-11", "2027-06-30", 42000, "planificacion",
        [("admin@demo.com", "Project Manager"), ("dev@demo.com", "Desarrollador full stack")],
        [("Levantamiento de requisitos", "2027-01-11", "2027-02-05", "pendiente")],
    ),
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


def sembrar_proyectos(conexion):
    """Solo carga los proyectos de prueba si todavía no hay ninguno."""
    if conexion.execute("SELECT 1 FROM proyectos").fetchone():
        return 0
    for nombre, descripcion, objetivos, inicio, fin, presupuesto, estado, miembros, fases in PROYECTOS_PRUEBA:
        proyecto_id = conexion.execute(
            "INSERT INTO proyectos (nombre, descripcion, objetivos, fecha_inicio, fecha_fin, presupuesto, estado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nombre, descripcion, objetivos, inicio, fin, presupuesto, estado),
        ).lastrowid
        for correo, rol_proyecto in miembros:
            conexion.execute(
                "INSERT INTO miembros_proyecto (proyecto_id, usuario_id, rol_proyecto) "
                "SELECT ?, id, ? FROM usuarios WHERE correo = ?",
                (proyecto_id, rol_proyecto, correo),
            )
        for orden, (fase, fase_inicio, fase_fin, fase_estado) in enumerate(fases, start=1):
            conexion.execute(
                "INSERT INTO fases (proyecto_id, nombre, orden, fecha_inicio, fecha_fin, estado) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (proyecto_id, fase, orden, fase_inicio, fase_fin, fase_estado),
            )
    conexion.commit()
    return len(PROYECTOS_PRUEBA)


def inicializar(ruta=RUTA_BD, con_datos=False):
    conexion = abrir(ruta)
    migrar(conexion)
    if con_datos:
        sembrar(conexion)
        sembrar_proyectos(conexion)
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


# --- Proyectos ---------------------------------------------------------------
CONSULTA_PROYECTO = """
    SELECT p.*,
           (SELECT COUNT(*) FROM miembros_proyecto m WHERE m.proyecto_id = p.id) AS num_miembros,
           (SELECT COUNT(*) FROM fases f WHERE f.proyecto_id = p.id) AS num_fases,
           (SELECT COUNT(*) FROM fases f WHERE f.proyecto_id = p.id AND f.estado = 'completada') AS fases_completadas
    FROM proyectos p
"""


def valores_proyecto(datos):
    return (
        datos["nombre"].strip(),
        datos.get("descripcion", "").strip(),
        datos.get("objetivos", "").strip(),
        datos["fecha_inicio"],
        datos["fecha_fin"],
        float(datos["presupuesto"]),
        datos["estado"],
    )


def listar_proyectos(texto="", estado=""):
    sql = CONSULTA_PROYECTO + " WHERE 1 = 1"
    parametros = []
    if texto:
        sql += " AND (p.nombre LIKE ? OR p.descripcion LIKE ?)"
        parametros += [f"%{texto}%", f"%{texto}%"]
    if estado in ESTADOS_PROYECTO:
        sql += " AND p.estado = ?"
        parametros.append(estado)
    return obtener_conexion().execute(sql + " ORDER BY p.fecha_inicio, p.id", parametros).fetchall()


def obtener_proyecto(proyecto_id):
    return obtener_conexion().execute(CONSULTA_PROYECTO + " WHERE p.id = ?", (proyecto_id,)).fetchone()


def crear_proyecto(datos):
    conexion = obtener_conexion()
    cursor = conexion.execute(
        "INSERT INTO proyectos (nombre, descripcion, objetivos, fecha_inicio, fecha_fin, presupuesto, estado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        valores_proyecto(datos),
    )
    conexion.commit()
    return cursor.lastrowid


def actualizar_proyecto(proyecto_id, datos):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE proyectos SET nombre = ?, descripcion = ?, objetivos = ?, fecha_inicio = ?, fecha_fin = ?, "
        "presupuesto = ?, estado = ? WHERE id = ?",
        valores_proyecto(datos) + (proyecto_id,),
    )
    conexion.commit()


def eliminar_proyecto(proyecto_id):
    """Borra también sus miembros y fases (ON DELETE CASCADE)."""
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))
    conexion.commit()


# --- Miembros del equipo -----------------------------------------------------
def listar_miembros(proyecto_id):
    return obtener_conexion().execute(
        "SELECT m.rol_proyecto, m.asignado, u.id, u.nombre, u.correo, u.activo, r.etiqueta AS rol_etiqueta "
        "FROM miembros_proyecto m JOIN usuarios u ON u.id = m.usuario_id JOIN roles r ON r.id = u.rol_id "
        "WHERE m.proyecto_id = ? ORDER BY u.nombre",
        (proyecto_id,),
    ).fetchall()


def usuarios_disponibles(proyecto_id):
    """Usuarios activos que todavía no forman parte del proyecto."""
    return obtener_conexion().execute(
        CONSULTA_USUARIO + " WHERE u.activo = 1 AND u.id NOT IN "
        "(SELECT usuario_id FROM miembros_proyecto WHERE proyecto_id = ?) ORDER BY u.nombre",
        (proyecto_id,),
    ).fetchall()


def es_miembro(proyecto_id, usuario_id):
    fila = obtener_conexion().execute(
        "SELECT 1 FROM miembros_proyecto WHERE proyecto_id = ? AND usuario_id = ?", (proyecto_id, usuario_id)
    ).fetchone()
    return fila is not None


def asignar_miembro(proyecto_id, usuario_id, rol_proyecto):
    """Añade al usuario al equipo o, si ya estaba, le cambia el rol."""
    conexion = obtener_conexion()
    conexion.execute(
        "INSERT INTO miembros_proyecto (proyecto_id, usuario_id, rol_proyecto) VALUES (?, ?, ?) "
        "ON CONFLICT (proyecto_id, usuario_id) DO UPDATE SET rol_proyecto = excluded.rol_proyecto",
        (proyecto_id, usuario_id, rol_proyecto),
    )
    conexion.commit()


def quitar_miembro(proyecto_id, usuario_id):
    conexion = obtener_conexion()
    conexion.execute(
        "DELETE FROM miembros_proyecto WHERE proyecto_id = ? AND usuario_id = ?", (proyecto_id, usuario_id)
    )
    conexion.commit()


# --- Fases (EDT/WBS) ---------------------------------------------------------
def valores_fase(datos):
    return (
        datos["nombre"].strip(),
        datos.get("descripcion", "").strip(),
        int(datos["orden"]),
        datos["fecha_inicio"],
        datos["fecha_fin"],
        datos["estado"],
    )


def listar_fases(proyecto_id):
    return obtener_conexion().execute(
        "SELECT * FROM fases WHERE proyecto_id = ? ORDER BY orden, fecha_inicio, id", (proyecto_id,)
    ).fetchall()


def obtener_fase(proyecto_id, fase_id):
    return obtener_conexion().execute(
        "SELECT * FROM fases WHERE proyecto_id = ? AND id = ?", (proyecto_id, fase_id)
    ).fetchone()


def siguiente_orden(proyecto_id):
    return obtener_conexion().execute(
        "SELECT COALESCE(MAX(orden), 0) + 1 FROM fases WHERE proyecto_id = ?", (proyecto_id,)
    ).fetchone()[0]


def rango_fases(proyecto_id, excluir_id=None):
    """(inicio más temprano, fin más tardío) de las fases del proyecto, o (None, None)."""
    fila = obtener_conexion().execute(
        "SELECT MIN(fecha_inicio), MAX(fecha_fin) FROM fases WHERE proyecto_id = ? AND id != ?",
        (proyecto_id, excluir_id or 0),
    ).fetchone()
    return fila[0], fila[1]


def crear_fase(proyecto_id, datos):
    conexion = obtener_conexion()
    cursor = conexion.execute(
        "INSERT INTO fases (nombre, descripcion, orden, fecha_inicio, fecha_fin, estado, proyecto_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        valores_fase(datos) + (proyecto_id,),
    )
    conexion.commit()
    return cursor.lastrowid


def actualizar_fase(fase_id, datos):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE fases SET nombre = ?, descripcion = ?, orden = ?, fecha_inicio = ?, fecha_fin = ?, estado = ? "
        "WHERE id = ?",
        valores_fase(datos) + (fase_id,),
    )
    conexion.commit()


def eliminar_fase(fase_id):
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM fases WHERE id = ?", (fase_id,))
    conexion.commit()


if __name__ == "__main__":
    if "--reiniciar" in sys.argv and os.path.exists(RUTA_BD):
        os.remove(RUTA_BD)
        print("Base de datos eliminada.")
    conexion = abrir(RUTA_BD)
    migrar(conexion)
    print(f"{sembrar(conexion)} usuarios de prueba creados (contraseña: {CONTRASENA_PRUEBA}).")
    print(f"{sembrar_proyectos(conexion)} proyectos de prueba creados.")
    conexion.close()
