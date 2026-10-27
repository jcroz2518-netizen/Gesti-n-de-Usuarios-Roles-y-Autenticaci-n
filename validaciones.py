"""Validaciones de los formularios. Cada función devuelve un diccionario
{campo: mensaje de error}; si está vacío, los datos son válidos."""
import re

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
