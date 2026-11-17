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
    # 3 - tareas de cada fase y registro de horas reales invertidas
    """
    CREATE TABLE tareas (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        fase_id         INTEGER NOT NULL REFERENCES fases(id) ON DELETE CASCADE,
        titulo          TEXT NOT NULL,
        descripcion     TEXT NOT NULL DEFAULT '',
        prioridad       TEXT NOT NULL DEFAULT 'media'
                        CHECK (prioridad IN ('baja', 'media', 'alta', 'critica')),
        responsable_id  INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
        estado          TEXT NOT NULL DEFAULT 'por_hacer'
                        CHECK (estado IN ('por_hacer', 'en_progreso', 'en_revision', 'concluida')),
        horas_estimadas REAL NOT NULL DEFAULT 0 CHECK (horas_estimadas >= 0),
        creado          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        actualizado     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE registros_horas (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        tarea_id   INTEGER NOT NULL REFERENCES tareas(id) ON DELETE CASCADE,
        usuario_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
        fecha      TEXT NOT NULL,
        horas      REAL NOT NULL CHECK (horas > 0),
        nota       TEXT NOT NULL DEFAULT '',
        creado     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX idx_tareas_fase ON tareas (fase_id);
    CREATE INDEX idx_tareas_responsable ON tareas (responsable_id);
    CREATE INDEX idx_registros_tarea ON registros_horas (tarea_id);
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

PRIORIDADES = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}

# El orden de las claves es el de las columnas del tablero Kanban
ESTADOS_TAREA = {
    "por_hacer": "Por hacer",
    "en_progreso": "En progreso",
    "en_revision": "En revisión",
    "concluida": "Concluida",
}

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

# (proyecto, fase, título, prioridad, responsable, estado, horas estimadas, [(fecha, horas, nota)])
# Las horas las registra el responsable de la tarea.
TAREAS_PRUEBA = [
    ("Portal de clientes", "Análisis de requisitos", "Entrevistas con el cliente", "media", "pm@demo.com",
     "concluida", 16, [("2026-09-08", 6, "Reunión con atención al cliente"), ("2026-09-10", 8, "")]),
    ("Portal de clientes", "Análisis de requisitos", "Documento de requisitos", "alta", "pm@demo.com",
     "concluida", 24, [("2026-09-22", 12, ""), ("2026-09-25", 10, "Revisión con el cliente")]),
    ("Portal de clientes", "Diseño", "Modelo de base de datos", "alta", "dev@demo.com",
     "concluida", 20, [("2026-10-07", 9, ""), ("2026-10-09", 14, "Normalización y relaciones")]),
    ("Portal de clientes", "Diseño", "Prototipo de pantallas", "media", "dev2@demo.com",
     "concluida", 30, [("2026-10-14", 12, ""), ("2026-10-20", 16, "Ajustes tras la revisión")]),
    ("Portal de clientes", "Desarrollo", "API de autenticación", "critica", "dev@demo.com",
     "en_revision", 24, [("2026-11-03", 8, ""), ("2026-11-05", 10, "Pruebas unitarias")]),
    ("Portal de clientes", "Desarrollo", "Módulo de pedidos", "alta", "dev@demo.com",
     "en_progreso", 40, [("2026-11-10", 7, "")]),
    ("Portal de clientes", "Desarrollo", "Pantalla de facturas", "media", "dev2@demo.com",
     "en_progreso", 32, [("2026-11-09", 6, "")]),
    ("Portal de clientes", "Desarrollo", "Notificaciones por correo", "baja", None, "por_hacer", 12, []),
    ("Portal de clientes", "Pruebas", "Plan de pruebas", "media", "dev2@demo.com", "por_hacer", 10, []),
    ("App móvil de inventario", "Levantamiento de requisitos", "Reunión con el equipo de almacén", "alta",
     "admin@demo.com", "por_hacer", 6, []),
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


def sembrar_tareas(conexion):
    """Solo carga las tareas de prueba si todavía no hay ninguna.
    Se salta las que apuntan a un proyecto o fase que ya no existe."""
    if conexion.execute("SELECT 1 FROM tareas").fetchone():
        return 0
    creadas = 0
    for proyecto, fase, titulo, prioridad, correo, estado, horas, registros in TAREAS_PRUEBA:
        fila_fase = conexion.execute(
            "SELECT f.id FROM fases f JOIN proyectos p ON p.id = f.proyecto_id WHERE p.nombre = ? AND f.nombre = ?",
            (proyecto, fase),
        ).fetchone()
        if fila_fase is None:
            continue
        fila_usuario = conexion.execute("SELECT id FROM usuarios WHERE correo = ?", (correo or "",)).fetchone()
        responsable_id = fila_usuario["id"] if fila_usuario else None
        tarea_id = conexion.execute(
            "INSERT INTO tareas (fase_id, titulo, prioridad, responsable_id, estado, horas_estimadas) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fila_fase["id"], titulo, prioridad, responsable_id, estado, horas),
        ).lastrowid
        for fecha, horas_reales, nota in registros:
            conexion.execute(
                "INSERT INTO registros_horas (tarea_id, usuario_id, fecha, horas, nota) VALUES (?, ?, ?, ?, ?)",
                (tarea_id, responsable_id, fecha, horas_reales, nota),
            )
        creadas += 1
    conexion.commit()
    return creadas


def inicializar(ruta=RUTA_BD, con_datos=False):
    conexion = abrir(ruta)
    migrar(conexion)
    if con_datos:
        sembrar(conexion)
        sembrar_proyectos(conexion)
        sembrar_tareas(conexion)
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
    """Lo saca del equipo y deja sin responsable sus tareas de ese proyecto (sus horas se conservan)."""
    conexion = obtener_conexion()
    conexion.execute(
        "DELETE FROM miembros_proyecto WHERE proyecto_id = ? AND usuario_id = ?", (proyecto_id, usuario_id)
    )
    conexion.execute(
        "UPDATE tareas SET responsable_id = NULL "
        "WHERE responsable_id = ? AND fase_id IN (SELECT id FROM fases WHERE proyecto_id = ?)",
        (usuario_id, proyecto_id),
    )
    conexion.commit()


def proyectos_de_usuario(usuario_id=None):
    """Todos los proyectos (usuario_id=None) o solo aquellos de los que el usuario es miembro."""
    if usuario_id is None:
        return obtener_conexion().execute("SELECT id, nombre FROM proyectos ORDER BY nombre").fetchall()
    return obtener_conexion().execute(
        "SELECT p.id, p.nombre FROM proyectos p JOIN miembros_proyecto m ON m.proyecto_id = p.id "
        "WHERE m.usuario_id = ? ORDER BY p.nombre",
        (usuario_id,),
    ).fetchall()


def miembros_de_proyectos(proyecto_ids):
    """Usuarios distintos que forman parte de alguno de esos proyectos (para filtrar por responsable)."""
    if not proyecto_ids:
        return []
    marcas = ", ".join("?" * len(proyecto_ids))
    return obtener_conexion().execute(
        f"SELECT DISTINCT u.id, u.nombre FROM usuarios u JOIN miembros_proyecto m ON m.usuario_id = u.id "
        f"WHERE m.proyecto_id IN ({marcas}) ORDER BY u.nombre",
        list(proyecto_ids),
    ).fetchall()


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
    """Fases del proyecto con el resumen de sus tareas (número y horas estimadas/reales)."""
    return obtener_conexion().execute(
        """
        SELECT f.*,
               (SELECT COUNT(*) FROM tareas t WHERE t.fase_id = f.id) AS num_tareas,
               (SELECT COALESCE(SUM(t.horas_estimadas), 0) FROM tareas t WHERE t.fase_id = f.id) AS horas_estimadas,
               (SELECT COALESCE(SUM(h.horas), 0) FROM registros_horas h JOIN tareas t ON t.id = h.tarea_id
                WHERE t.fase_id = f.id) AS horas_reales
        FROM fases f WHERE f.proyecto_id = ? ORDER BY f.orden, f.fecha_inicio, f.id
        """,
        (proyecto_id,),
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


def contar_tareas_fase(fase_id):
    return obtener_conexion().execute("SELECT COUNT(*) FROM tareas WHERE fase_id = ?", (fase_id,)).fetchone()[0]


# --- Tareas ------------------------------------------------------------------
CONSULTA_TAREA = """
    SELECT t.*, f.nombre AS fase, f.orden AS fase_orden, f.proyecto_id, p.nombre AS proyecto,
           u.nombre AS responsable,
           (SELECT COALESCE(SUM(h.horas), 0) FROM registros_horas h WHERE h.tarea_id = t.id) AS horas_reales
    FROM tareas t
    JOIN fases f ON f.id = t.fase_id
    JOIN proyectos p ON p.id = f.proyecto_id
    LEFT JOIN usuarios u ON u.id = t.responsable_id
"""

ORDEN_PRIORIDAD = "CASE t.prioridad WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END"


def valores_tarea(datos):
    return (
        int(datos["fase_id"]),
        datos["titulo"].strip(),
        datos.get("descripcion", "").strip(),
        datos["prioridad"],
        int(datos["responsable_id"]) if datos.get("responsable_id") else None,
        datos["estado"],
        float(datos["horas_estimadas"]),
    )


def listar_tareas(texto="", proyecto="", responsable="", estado="", prioridad="", miembro_id=None):
    """Filtros opcionales. responsable puede ser un id o "ninguno" (sin asignar).
    Con miembro_id solo devuelve tareas de proyectos de los que ese usuario es miembro."""
    sql = CONSULTA_TAREA + " WHERE 1 = 1"
    parametros = []
    if texto:
        sql += " AND (t.titulo LIKE ? OR t.descripcion LIKE ?)"
        parametros += [f"%{texto}%", f"%{texto}%"]
    if str(proyecto).isdigit():
        sql += " AND f.proyecto_id = ?"
        parametros.append(int(proyecto))
    if responsable == "ninguno":
        sql += " AND t.responsable_id IS NULL"
    elif str(responsable).isdigit():
        sql += " AND t.responsable_id = ?"
        parametros.append(int(responsable))
    if estado in ESTADOS_TAREA:
        sql += " AND t.estado = ?"
        parametros.append(estado)
    if prioridad in PRIORIDADES:
        sql += " AND t.prioridad = ?"
        parametros.append(prioridad)
    if miembro_id is not None:
        sql += " AND f.proyecto_id IN (SELECT proyecto_id FROM miembros_proyecto WHERE usuario_id = ?)"
        parametros.append(miembro_id)
    sql += f" ORDER BY {ORDEN_PRIORIDAD}, p.nombre, f.orden, t.id"
    return obtener_conexion().execute(sql, parametros).fetchall()


def obtener_tarea(tarea_id):
    return obtener_conexion().execute(CONSULTA_TAREA + " WHERE t.id = ?", (tarea_id,)).fetchone()


def crear_tarea(datos):
    conexion = obtener_conexion()
    cursor = conexion.execute(
        "INSERT INTO tareas (fase_id, titulo, descripcion, prioridad, responsable_id, estado, horas_estimadas) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        valores_tarea(datos),
    )
    conexion.commit()
    return cursor.lastrowid


def actualizar_tarea(tarea_id, datos):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE tareas SET fase_id = ?, titulo = ?, descripcion = ?, prioridad = ?, responsable_id = ?, "
        "estado = ?, horas_estimadas = ?, actualizado = CURRENT_TIMESTAMP WHERE id = ?",
        valores_tarea(datos) + (tarea_id,),
    )
    conexion.commit()


def cambiar_estado_tarea(tarea_id, estado):
    conexion = obtener_conexion()
    conexion.execute(
        "UPDATE tareas SET estado = ?, actualizado = CURRENT_TIMESTAMP WHERE id = ?", (estado, tarea_id)
    )
    conexion.commit()


def eliminar_tarea(tarea_id):
    """Borra también sus registros de horas (ON DELETE CASCADE)."""
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM tareas WHERE id = ?", (tarea_id,))
    conexion.commit()


# --- Registro de horas reales ------------------------------------------------
def listar_registros(tarea_id):
    return obtener_conexion().execute(
        "SELECT h.*, u.nombre AS usuario FROM registros_horas h LEFT JOIN usuarios u ON u.id = h.usuario_id "
        "WHERE h.tarea_id = ? ORDER BY h.fecha DESC, h.id DESC",
        (tarea_id,),
    ).fetchall()


def obtener_registro(tarea_id, registro_id):
    return obtener_conexion().execute(
        "SELECT * FROM registros_horas WHERE tarea_id = ? AND id = ?", (tarea_id, registro_id)
    ).fetchone()


def registrar_horas(tarea_id, usuario_id, fecha, horas, nota=""):
    conexion = obtener_conexion()
    conexion.execute(
        "INSERT INTO registros_horas (tarea_id, usuario_id, fecha, horas, nota) VALUES (?, ?, ?, ?, ?)",
        (tarea_id, usuario_id, fecha, float(horas), nota.strip()),
    )
    conexion.commit()


def eliminar_registro(registro_id):
    conexion = obtener_conexion()
    conexion.execute("DELETE FROM registros_horas WHERE id = ?", (registro_id,))
    conexion.commit()


if __name__ == "__main__":
    if "--reiniciar" in sys.argv and os.path.exists(RUTA_BD):
        os.remove(RUTA_BD)
        print("Base de datos eliminada.")
    conexion = abrir(RUTA_BD)
    migrar(conexion)
    print(f"{sembrar(conexion)} usuarios de prueba creados (contraseña: {CONTRASENA_PRUEBA}).")
    print(f"{sembrar_proyectos(conexion)} proyectos de prueba creados.")
    print(f"{sembrar_tareas(conexion)} tareas de prueba creadas.")
    conexion.close()
