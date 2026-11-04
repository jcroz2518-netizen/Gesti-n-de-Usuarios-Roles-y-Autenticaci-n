"""Validaciones de los formularios. Cada función devuelve un diccionario
{campo: mensaje de error}; si está vacío, los datos son válidos."""
import math
import re
from datetime import date

import base_datos

PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")

REGLAS_CONTRASENA = [
    (r".{8,}", "al menos 8 caracteres"),
    (r"[A-Z]", "una mayúscula"),
    (r"[a-z]", "una minúscula"),
    (r"\d", "un número"),
    (r"[^A-Za-z0-9]", "un carácter especial"),
]


def validar_nombre(nombre):
    nombre = nombre.strip()
    if not nombre:
        return "El nombre es obligatorio."
    if len(nombre) < 3 or len(nombre) > 120:
        return "El nombre debe tener entre 3 y 120 caracteres."
    return None


def validar_correo(correo, excluir_id=None):
    correo = correo.strip()
    if not correo:
        return "El correo es obligatorio."
    if len(correo) > 120 or not PATRON_CORREO.match(correo):
        return "El correo no es válido."
    if base_datos.correo_existe(correo, excluir_id):
        return "Ya existe un usuario con ese correo."
    return None


def validar_contrasena(contrasena, confirmacion):
    if not contrasena:
        return "La contraseña es obligatoria."
    faltan = [mensaje for patron, mensaje in REGLAS_CONTRASENA if not re.search(patron, contrasena)]
    if faltan:
        return "La contraseña debe tener " + ", ".join(faltan) + "."
    if contrasena != confirmacion:
        return "Las contraseñas no coinciden."
    return None


def validar_registro(datos):
    errores = {
        "nombre": validar_nombre(datos.get("nombre", "")),
        "correo": validar_correo(datos.get("correo", "")),
        "contrasena": validar_contrasena(datos.get("contrasena", ""), datos.get("confirmacion", "")),
    }
    return {campo: error for campo, error in errores.items() if error}


def validar_usuario(datos, usuario_id=None):
    """Alta (usuario_id=None, contraseña obligatoria) o edición (contraseña opcional)."""
    errores = {
        "nombre": validar_nombre(datos.get("nombre", "")),
        "correo": validar_correo(datos.get("correo", ""), usuario_id),
    }
    roles_validos = {str(rol["id"]) for rol in base_datos.listar_roles()}
    if datos.get("rol_id") not in roles_validos:
        errores["rol_id"] = "Selecciona un rol válido."
    if usuario_id is None or datos.get("contrasena"):
        errores["contrasena"] = validar_contrasena(datos.get("contrasena", ""), datos.get("confirmacion", ""))
    return {campo: error for campo, error in errores.items() if error}


# --- Proyectos y fases -------------------------------------------------------
def leer_fecha(valor):
    try:
        return date.fromisoformat((valor or "").strip())
    except ValueError:
        return None


def validar_texto_largo(texto, maximo=2000):
    if len(texto.strip()) > maximo:
        return f"Máximo {maximo} caracteres."
    return None


def validar_fechas(datos, errores):
    """Comprueba fecha_inicio y fecha_fin; devuelve (inicio, fin) si ambas son válidas."""
    inicio, fin = leer_fecha(datos.get("fecha_inicio")), leer_fecha(datos.get("fecha_fin"))
    if inicio is None:
        errores["fecha_inicio"] = "Indica una fecha de inicio válida."
    if fin is None:
        errores["fecha_fin"] = "Indica una fecha de fin válida."
    elif inicio and fin < inicio:
        errores["fecha_fin"] = "La fecha de fin no puede ser anterior a la de inicio."
    if errores.get("fecha_inicio") or errores.get("fecha_fin"):
        return None, None
    return inicio, fin


def validar_proyecto(datos, proyecto_id=None):
    errores = {
        "nombre": validar_nombre(datos.get("nombre", "")),
        "descripcion": validar_texto_largo(datos.get("descripcion", "")),
        "objetivos": validar_texto_largo(datos.get("objetivos", "")),
    }
    inicio, fin = validar_fechas(datos, errores)
    try:
        presupuesto = float(datos.get("presupuesto", "").strip())
        if not math.isfinite(presupuesto) or presupuesto < 0:
            raise ValueError
    except ValueError:
        errores["presupuesto"] = "El presupuesto debe ser un número mayor o igual a 0."
    if datos.get("estado") not in base_datos.ESTADOS_PROYECTO:
        errores["estado"] = "Selecciona un estado válido."
    if proyecto_id and inicio:
        # Al editar, las fases existentes deben seguir dentro de las fechas del proyecto.
        primera, ultima = base_datos.rango_fases(proyecto_id)
        if primera and (primera < inicio.isoformat() or ultima > fin.isoformat()):
            errores["fecha_fin"] = f"Hay fases entre {primera} y {ultima}; ajústalas antes de cambiar estas fechas."
    return {campo: error for campo, error in errores.items() if error}


def validar_fase(datos, proyecto):
    errores = {
        "nombre": validar_nombre(datos.get("nombre", "")),
        "descripcion": validar_texto_largo(datos.get("descripcion", "")),
    }
    if not datos.get("orden", "").strip().isdigit() or int(datos["orden"]) < 1:
        errores["orden"] = "El orden debe ser un número entero mayor que 0."
    inicio, fin = validar_fechas(datos, errores)
    if inicio and (inicio.isoformat() < proyecto["fecha_inicio"] or fin.isoformat() > proyecto["fecha_fin"]):
        errores["fecha_fin"] = (
            f"La fase debe estar dentro de las fechas del proyecto "
            f"({proyecto['fecha_inicio']} a {proyecto['fecha_fin']})."
        )
    if datos.get("estado") not in base_datos.ESTADOS_FASE:
        errores["estado"] = "Selecciona un estado válido."
    return {campo: error for campo, error in errores.items() if error}


def validar_miembro(datos, proyecto_id):
    """Devuelve un mensaje de error o None. Solo se añaden usuarios activos;
    a quien ya es miembro se le puede cambiar el rol aunque esté inactivo."""
    usuario_id = datos.get("usuario_id", "")
    if not usuario_id.isdigit():
        return "Selecciona un usuario."
    usuario = base_datos.obtener_usuario(int(usuario_id))
    if usuario is None:
        return "El usuario no existe."
    if not usuario["activo"] and not base_datos.es_miembro(proyecto_id, usuario["id"]):
        return "No se pueden asignar usuarios inactivos."
    if datos.get("rol_proyecto") not in base_datos.ROLES_PROYECTO:
        return "Selecciona un rol válido para el proyecto."
    return None
