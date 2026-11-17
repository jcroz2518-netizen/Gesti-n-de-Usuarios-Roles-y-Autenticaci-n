import os
import secrets
import smtplib
from datetime import date, timedelta
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

import base_datos
import validaciones
from base_datos import ADMIN, CLIENTE, DESARROLLADOR

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-insegura-cambiar")
app.config["BASE_DATOS"] = base_datos.RUTA_BD
app.config["CSRF_ACTIVO"] = True
app.config["CADUCIDAD_ENLACE"] = 3600  # segundos que vale el enlace de recuperación
app.permanent_session_lifetime = timedelta(days=30)  # duración de "Recordarme"

app.teardown_appcontext(base_datos.cerrar_conexion)
base_datos.inicializar(app.config["BASE_DATOS"])  # aplica migraciones pendientes al arrancar


# ---------------------------------------------------------------------------
# Sesión, CSRF y decoradores de acceso
# ---------------------------------------------------------------------------
@app.before_request
def cargar_usuario():
    g.usuario = None
    usuario_id = session.get("usuario_id")
    if usuario_id is not None:
        usuario = base_datos.obtener_usuario(usuario_id)
        if usuario is None or not usuario["activo"]:
            # Usuario eliminado o desactivado: se cierra su sesión.
            session.clear()
        else:
            g.usuario = usuario


@app.before_request
def proteger_csrf():
    if request.method == "POST" and app.config["CSRF_ACTIVO"]:
        token = session.get("csrf_token", "")
        if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
            abort(400)


def token_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = token_csrf


@app.context_processor
def datos_plantillas():
    return {
        "usuario_actual": g.get("usuario"), "ADMIN": ADMIN, "DESARROLLADOR": DESARROLLADOR, "CLIENTE": CLIENTE,
        "ESTADOS_PROYECTO": base_datos.ESTADOS_PROYECTO, "ESTADOS_FASE": base_datos.ESTADOS_FASE,
        "ROLES_PROYECTO": base_datos.ROLES_PROYECTO, "PRIORIDADES": base_datos.PRIORIDADES,
        "ESTADOS_TAREA": base_datos.ESTADOS_TAREA,
    }


@app.template_filter("moneda")
def moneda(valor):
    return f"$ {valor:,.2f}"


@app.template_filter("horas")
def horas(valor):
    """12.0 -> "12 h", 7.5 -> "7.5 h" """
    return f"{valor:,.2f}".rstrip("0").rstrip(".") + " h"


def ruta_segura(siguiente, defecto):
    """Solo rutas internas, para evitar redirecciones a otros sitios."""
    if (not siguiente or not siguiente.startswith("/") or siguiente.startswith(("//", "/\\"))
            or urlsplit(siguiente).netloc):
        return defecto
    return siguiente


def login_requerido(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if g.usuario is None:
            flash("Inicia sesión para acceder a esta página.", "warning")
            return redirect(url_for("login", next=request.path))
        return vista(*args, **kwargs)

    return envoltura


def rol_requerido(*roles):
    """Sin sesión -> login. Con sesión pero rol no permitido -> 403."""

    def decorador(vista):
        @wraps(vista)
        @login_requerido
        def envoltura(*args, **kwargs):
            if g.usuario["rol"] not in roles:
                abort(403)
            return vista(*args, **kwargs)

        return envoltura

    return decorador


# ---------------------------------------------------------------------------
# Recuperación de contraseña
# El token lleva parte del hash de la contraseña: al cambiarla, el enlace deja de valer.
# ---------------------------------------------------------------------------
def serializador():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="recuperar-contrasena")


def generar_token(usuario):
    return serializador().dumps({"id": usuario["id"], "h": usuario["contrasena"][-12:]})


def verificar_token(token):
    try:
        datos = serializador().loads(token, max_age=app.config["CADUCIDAD_ENLACE"])
    except (SignatureExpired, BadSignature):
        return None
    usuario = base_datos.obtener_usuario(datos.get("id"))
    if usuario is None or usuario["contrasena"][-12:] != datos.get("h"):
        return None
    return usuario


def enviar_correo_recuperacion(usuario):
    enlace = url_for("restablecer", token=generar_token(usuario), _external=True)
    servidor = os.environ.get("SMTP_SERVIDOR")
    if not servidor:
        # Sin SMTP configurado (desarrollo): el enlace se muestra en la consola.
        print(f"[RECUPERACIÓN] Enlace para {usuario['correo']}: {enlace}")
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = "Recuperación de contraseña"
    mensaje["From"] = os.environ.get("SMTP_REMITENTE", os.environ.get("SMTP_USUARIO", ""))
    mensaje["To"] = usuario["correo"]
    mensaje.set_content(
        f"Hola {usuario['nombre']},\n\nPara restablecer tu contraseña entra en:\n{enlace}\n\n"
        "Si no solicitaste el cambio, ignora este correo."
    )
    with smtplib.SMTP(servidor, int(os.environ.get("SMTP_PUERTO", 587))) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USUARIO"], os.environ["SMTP_CONTRASENA"])
        smtp.send_message(mensaje)


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
@app.route("/")
def inicio():
    return redirect(url_for("panel" if g.usuario else "login"))


@app.route("/registro", methods=["GET", "POST"])
def registro():
    if g.usuario:
        return redirect(url_for("panel"))

    datos, errores = {}, {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_registro(datos)
        if not errores:
            # El registro público siempre crea Clientes; el Administrador asigna otros roles.
            rol_cliente = next(r for r in base_datos.listar_roles() if r["nombre"] == CLIENTE)
            base_datos.crear_usuario(datos["nombre"], datos["correo"], datos["contrasena"], rol_cliente["id"])
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
    return render_template("registro.html", datos=datos, errores=errores)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("panel"))

    correo = ""
    if request.method == "POST":
        correo = request.form.get("correo", "").strip()
        usuario = base_datos.buscar_usuario_por_correo(correo)
        if usuario is None or not check_password_hash(usuario["contrasena"], request.form.get("contrasena", "")):
            flash("Correo o contraseña incorrectos.", "danger")
        elif not usuario["activo"]:
            flash("Tu cuenta está inactiva. Contacta con un administrador.", "warning")
        else:
            session.clear()  # sesión nueva al entrar
            session["usuario_id"] = usuario["id"]
            session.permanent = "recordar" in request.form
            base_datos.registrar_acceso(usuario["id"])
            return redirect(ruta_segura(request.args.get("next"), url_for("panel")))
    return render_template("login.html", correo=correo)


@app.route("/logout", methods=["POST"])
@login_requerido
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))


@app.route("/recuperar", methods=["GET", "POST"])
def recuperar():
    if request.method == "POST":
        usuario = base_datos.buscar_usuario_por_correo(request.form.get("correo", ""))
        if usuario and usuario["activo"]:
            enviar_correo_recuperacion(usuario)
        # Mismo mensaje exista o no el correo, para no revelar qué cuentas hay.
        flash("Si el correo está registrado, recibirás un enlace para restablecer la contraseña.", "info")
        return redirect(url_for("login"))
    return render_template("recuperar.html")


@app.route("/restablecer/<token>", methods=["GET", "POST"])
def restablecer(token):
    usuario = verificar_token(token)
    if usuario is None:
        flash("El enlace no es válido o ha caducado.", "danger")
        return redirect(url_for("recuperar"))

    errores = {}
    if request.method == "POST":
        error = validaciones.validar_contrasena(request.form.get("contrasena", ""), request.form.get("confirmacion", ""))
        if error:
            errores["contrasena"] = error
        else:
            base_datos.cambiar_contrasena(usuario["id"], request.form["contrasena"])
            flash("Contraseña actualizada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
    return render_template("restablecer.html", errores=errores)


# ---------------------------------------------------------------------------
# Panel y secciones por rol
# Informes es de momento una página de demostración del control de acceso;
# su módulo se construirá encima.
# ---------------------------------------------------------------------------
@app.route("/panel")
@login_requerido
def panel():
    return render_template("panel.html")


@app.route("/informes")
@rol_requerido(ADMIN, DESARROLLADOR, CLIENTE)
def informes():
    return render_template("seccion.html", titulo="Informes",
                           texto="Informes, métricas y estado de los proyectos (solo lectura para clientes).")


# ---------------------------------------------------------------------------
# CRUD de usuarios (solo Administrador)
# ---------------------------------------------------------------------------
def usuario_o_404(usuario_id):
    usuario = base_datos.obtener_usuario(usuario_id)
    if usuario is None:
        abort(404)
    return usuario


@app.route("/usuarios")
@rol_requerido(ADMIN)
def usuarios():
    lista = base_datos.listar_usuarios(
        request.args.get("q", "").strip(), request.args.get("rol", ""), request.args.get("estado", "")
    )
    return render_template("usuarios.html", usuarios=lista, roles=base_datos.listar_roles())


@app.route("/usuarios/nuevo", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def usuario_nuevo():
    datos, errores = {"activo": "1"}, {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_usuario(datos)
        if not errores:
            base_datos.crear_usuario(
                datos["nombre"], datos["correo"], datos["contrasena"], int(datos["rol_id"]), "activo" in datos
            )
            flash(f"Usuario {datos['correo'].strip().lower()} creado.", "success")
            return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", titulo="Nuevo usuario", datos=datos, errores=errores,
                           roles=base_datos.listar_roles())


@app.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def usuario_editar(usuario_id):
    usuario = usuario_o_404(usuario_id)
    datos, errores = dict(usuario), {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_usuario(datos, usuario_id)
        es_el_mismo = usuario_id == g.usuario["id"]
        if es_el_mismo and ("activo" not in datos or datos.get("rol_id") != str(usuario["rol_id"])):
            errores["rol_id"] = "No puedes desactivarte ni quitarte el rol de administrador a ti mismo."
        if not errores:
            base_datos.actualizar_usuario(
                usuario_id, datos["nombre"], datos["correo"], int(datos["rol_id"]), "activo" in datos
            )
            if datos.get("contrasena"):
                base_datos.cambiar_contrasena(usuario_id, datos["contrasena"])
            flash("Usuario actualizado.", "success")
            return redirect(url_for("usuarios"))
    return render_template("usuario_form.html", titulo="Editar usuario", datos=datos, errores=errores,
                           roles=base_datos.listar_roles(), usuario=usuario)


@app.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
@rol_requerido(ADMIN)
def usuario_estado(usuario_id):
    usuario = usuario_o_404(usuario_id)
    if usuario_id == g.usuario["id"]:
        flash("No puedes desactivar tu propia cuenta.", "danger")
    else:
        base_datos.cambiar_estado(usuario_id)
        flash(f"Usuario {'desactivado' if usuario['activo'] else 'activado'}.", "success")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/eliminar", methods=["POST"])
@rol_requerido(ADMIN)
def usuario_eliminar(usuario_id):
    usuario_o_404(usuario_id)
    if usuario_id == g.usuario["id"]:
        flash("No puedes eliminar tu propia cuenta.", "danger")
    else:
        base_datos.eliminar_usuario(usuario_id)
        flash("Usuario eliminado.", "success")
    return redirect(url_for("usuarios"))


# ---------------------------------------------------------------------------
# Proyectos, miembros del equipo y fases (solo Administrador)
# ---------------------------------------------------------------------------
def proyecto_o_404(proyecto_id):
    proyecto = base_datos.obtener_proyecto(proyecto_id)
    if proyecto is None:
        abort(404)
    return proyecto


def fase_o_404(proyecto_id, fase_id):
    fase = base_datos.obtener_fase(proyecto_id, fase_id)
    if fase is None:
        abort(404)
    return fase


@app.route("/proyectos")
@rol_requerido(ADMIN)
def proyectos():
    lista = base_datos.listar_proyectos(request.args.get("q", "").strip(), request.args.get("estado", ""))
    return render_template("proyectos.html", proyectos=lista)


@app.route("/proyectos/nuevo", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def proyecto_nuevo():
    datos, errores = {"estado": "planificacion", "presupuesto": "0"}, {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_proyecto(datos)
        if not errores:
            proyecto_id = base_datos.crear_proyecto(datos)
            flash("Proyecto creado. Ahora puedes asignar el equipo y definir las fases.", "success")
            return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id))
    return render_template("proyecto_form.html", titulo="Nuevo proyecto", datos=datos, errores=errores)


@app.route("/proyectos/<int:proyecto_id>")
@rol_requerido(ADMIN)
def proyecto_detalle(proyecto_id):
    return render_template(
        "proyecto.html",
        proyecto=proyecto_o_404(proyecto_id),
        miembros=base_datos.listar_miembros(proyecto_id),
        disponibles=base_datos.usuarios_disponibles(proyecto_id),
        fases=base_datos.listar_fases(proyecto_id),
    )


@app.route("/proyectos/<int:proyecto_id>/editar", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def proyecto_editar(proyecto_id):
    proyecto = proyecto_o_404(proyecto_id)
    datos, errores = dict(proyecto), {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_proyecto(datos, proyecto_id)
        if not errores:
            base_datos.actualizar_proyecto(proyecto_id, datos)
            flash("Proyecto actualizado.", "success")
            return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id))
    return render_template("proyecto_form.html", titulo="Editar proyecto", datos=datos, errores=errores,
                           proyecto=proyecto)


@app.route("/proyectos/<int:proyecto_id>/eliminar", methods=["POST"])
@rol_requerido(ADMIN)
def proyecto_eliminar(proyecto_id):
    proyecto = proyecto_o_404(proyecto_id)
    base_datos.eliminar_proyecto(proyecto_id)
    flash(f"Proyecto «{proyecto['nombre']}» eliminado.", "success")
    return redirect(url_for("proyectos"))


@app.route("/proyectos/<int:proyecto_id>/miembros", methods=["POST"])
@rol_requerido(ADMIN)
def miembro_asignar(proyecto_id):
    """Añade un miembro o cambia su rol si ya estaba en el equipo."""
    proyecto_o_404(proyecto_id)
    error = validaciones.validar_miembro(request.form, proyecto_id)
    if error:
        flash(error, "danger")
    else:
        usuario_id = int(request.form["usuario_id"])
        ya_era_miembro = base_datos.es_miembro(proyecto_id, usuario_id)
        base_datos.asignar_miembro(proyecto_id, usuario_id, request.form["rol_proyecto"])
        flash("Rol actualizado." if ya_era_miembro else "Miembro añadido al equipo.", "success")
    return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id) + "#equipo")


@app.route("/proyectos/<int:proyecto_id>/miembros/<int:usuario_id>/quitar", methods=["POST"])
@rol_requerido(ADMIN)
def miembro_quitar(proyecto_id, usuario_id):
    proyecto_o_404(proyecto_id)
    if not base_datos.es_miembro(proyecto_id, usuario_id):
        abort(404)
    base_datos.quitar_miembro(proyecto_id, usuario_id)
    flash("Miembro retirado del equipo. Sus tareas en este proyecto quedan sin responsable.", "success")
    return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id) + "#equipo")


@app.route("/proyectos/<int:proyecto_id>/fases/nueva", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def fase_nueva(proyecto_id):
    proyecto = proyecto_o_404(proyecto_id)
    datos = {"orden": base_datos.siguiente_orden(proyecto_id), "estado": "pendiente",
             "fecha_inicio": proyecto["fecha_inicio"], "fecha_fin": proyecto["fecha_fin"]}
    errores = {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_fase(datos, proyecto)
        if not errores:
            base_datos.crear_fase(proyecto_id, datos)
            flash("Fase creada.", "success")
            return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id) + "#fases")
    return render_template("fase_form.html", titulo="Nueva fase", proyecto=proyecto, datos=datos, errores=errores)


@app.route("/proyectos/<int:proyecto_id>/fases/<int:fase_id>/editar", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def fase_editar(proyecto_id, fase_id):
    proyecto = proyecto_o_404(proyecto_id)
    datos, errores = dict(fase_o_404(proyecto_id, fase_id)), {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_fase(datos, proyecto)
        if not errores:
            base_datos.actualizar_fase(fase_id, datos)
            flash("Fase actualizada.", "success")
            return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id) + "#fases")
    return render_template("fase_form.html", titulo="Editar fase", proyecto=proyecto, datos=datos, errores=errores)


@app.route("/proyectos/<int:proyecto_id>/fases/<int:fase_id>/eliminar", methods=["POST"])
@rol_requerido(ADMIN)
def fase_eliminar(proyecto_id, fase_id):
    fase_o_404(proyecto_id, fase_id)
    num_tareas = base_datos.contar_tareas_fase(fase_id)
    if num_tareas:
        flash(f"La fase tiene {num_tareas} tarea(s); muévelas a otra fase o elimínalas antes.", "danger")
    else:
        base_datos.eliminar_fase(fase_id)
        flash("Fase eliminada.", "success")
    return redirect(url_for("proyecto_detalle", proyecto_id=proyecto_id) + "#fases")


# ---------------------------------------------------------------------------
# Tareas y registro de horas
# Administrador: todo. Desarrollador: ve las tareas de los proyectos de los que
# es miembro y, en las que es responsable, cambia el estado y registra horas.
# ---------------------------------------------------------------------------
def es_admin():
    return g.usuario["rol"] == ADMIN


def puede_trabajar(tarea):
    return es_admin() or tarea["responsable_id"] == g.usuario["id"]


app.jinja_env.globals["puede_trabajar"] = puede_trabajar


def tarea_o_404(tarea_id):
    tarea = base_datos.obtener_tarea(tarea_id)
    if tarea is None:
        abort(404)
    if not es_admin() and not base_datos.es_miembro(tarea["proyecto_id"], g.usuario["id"]):
        abort(403)
    return tarea


def formulario_tarea(titulo, proyecto, datos, errores, tarea=None):
    return render_template("tarea_form.html", titulo=titulo, proyecto=proyecto, datos=datos, errores=errores,
                           tarea=tarea, fases=base_datos.listar_fases(proyecto["id"]),
                           miembros=base_datos.listar_miembros(proyecto["id"]))


def detalle_tarea(tarea, datos=None, errores=None):
    hoy = date.today().isoformat()
    return render_template("tarea.html", tarea=tarea, registros=base_datos.listar_registros(tarea["id"]),
                           datos=datos or {"fecha": hoy}, errores=errores or {}, hoy=hoy)


@app.route("/tareas")
@rol_requerido(ADMIN, DESARROLLADOR)
def tareas():
    filtros = {campo: request.args.get(campo, "").strip()
               for campo in ("q", "proyecto", "responsable", "estado", "prioridad")}
    miembro_id = None if es_admin() else g.usuario["id"]
    lista = base_datos.listar_tareas(filtros["q"], filtros["proyecto"], filtros["responsable"],
                                     filtros["estado"], filtros["prioridad"], miembro_id)
    proyectos_visibles = base_datos.proyectos_de_usuario(miembro_id)
    return render_template(
        "tareas.html",
        tareas=lista,
        columnas={estado: [t for t in lista if t["estado"] == estado] for estado in base_datos.ESTADOS_TAREA},
        vista="kanban" if request.args.get("vista") == "kanban" else "lista",
        filtros=filtros,
        proyectos=proyectos_visibles,
        responsables=base_datos.miembros_de_proyectos([p["id"] for p in proyectos_visibles]),
    )


@app.route("/tareas/nueva", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def tarea_nueva():
    proyecto_id = request.args.get("proyecto", "")
    proyecto = base_datos.obtener_proyecto(int(proyecto_id)) if proyecto_id.isdigit() else None
    if proyecto is None:
        # Primer paso: elegir el proyecto, porque las fases y los responsables dependen de él.
        return render_template("tarea_proyecto.html", proyectos=base_datos.proyectos_de_usuario())

    datos = {"prioridad": "media", "estado": "por_hacer", "horas_estimadas": "0",
             "fase_id": request.args.get("fase", "")}
    errores = {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_tarea(datos, proyecto["id"])
        if not errores:
            tarea_id = base_datos.crear_tarea(datos)
            flash("Tarea creada.", "success")
            return redirect(url_for("tarea_detalle", tarea_id=tarea_id))
    return formulario_tarea("Nueva tarea", proyecto, datos, errores)


@app.route("/tareas/<int:tarea_id>")
@rol_requerido(ADMIN, DESARROLLADOR)
def tarea_detalle(tarea_id):
    return detalle_tarea(tarea_o_404(tarea_id))


@app.route("/tareas/<int:tarea_id>/editar", methods=["GET", "POST"])
@rol_requerido(ADMIN)
def tarea_editar(tarea_id):
    tarea = tarea_o_404(tarea_id)
    proyecto = base_datos.obtener_proyecto(tarea["proyecto_id"])
    datos, errores = dict(tarea), {}
    if request.method == "POST":
        datos = request.form
        errores = validaciones.validar_tarea(datos, proyecto["id"], tarea)
        if not errores:
            base_datos.actualizar_tarea(tarea_id, datos)
            flash("Tarea actualizada.", "success")
            return redirect(url_for("tarea_detalle", tarea_id=tarea_id))
    return formulario_tarea("Editar tarea", proyecto, datos, errores, tarea)


@app.route("/tareas/<int:tarea_id>/eliminar", methods=["POST"])
@rol_requerido(ADMIN)
def tarea_eliminar(tarea_id):
    tarea = tarea_o_404(tarea_id)
    base_datos.eliminar_tarea(tarea_id)
    flash(f"Tarea «{tarea['titulo']}» eliminada.", "success")
    return redirect(url_for("tareas"))


@app.route("/tareas/<int:tarea_id>/estado", methods=["POST"])
@rol_requerido(ADMIN, DESARROLLADOR)
def tarea_estado(tarea_id):
    """Mueve la tarea de columna en el tablero (o desde su detalle)."""
    tarea = tarea_o_404(tarea_id)
    if not puede_trabajar(tarea):
        abort(403)
    estado = request.form.get("estado")
    if estado not in base_datos.ESTADOS_TAREA:
        flash("Estado no válido.", "danger")
    elif estado != tarea["estado"]:
        base_datos.cambiar_estado_tarea(tarea_id, estado)
        flash(f"«{tarea['titulo']}» pasó a {base_datos.ESTADOS_TAREA[estado]}.", "success")
    return redirect(ruta_segura(request.form.get("next"), url_for("tarea_detalle", tarea_id=tarea_id)))


@app.route("/tareas/<int:tarea_id>/horas", methods=["POST"])
@rol_requerido(ADMIN, DESARROLLADOR)
def tarea_horas(tarea_id):
    tarea = tarea_o_404(tarea_id)
    if not puede_trabajar(tarea):
        abort(403)
    errores = validaciones.validar_registro_horas(request.form)
    if errores:
        return detalle_tarea(tarea, request.form, errores)
    base_datos.registrar_horas(tarea_id, g.usuario["id"], request.form["fecha"], request.form["horas"],
                               request.form.get("nota", ""))
    flash("Horas registradas.", "success")
    return redirect(url_for("tarea_detalle", tarea_id=tarea_id) + "#horas")


@app.route("/tareas/<int:tarea_id>/horas/<int:registro_id>/eliminar", methods=["POST"])
@rol_requerido(ADMIN, DESARROLLADOR)
def registro_eliminar(tarea_id, registro_id):
    tarea_o_404(tarea_id)
    registro = base_datos.obtener_registro(tarea_id, registro_id)
    if registro is None:
        abort(404)
    if not es_admin() and registro["usuario_id"] != g.usuario["id"]:
        abort(403)
    base_datos.eliminar_registro(registro_id)
    flash("Registro de horas eliminado.", "success")
    return redirect(url_for("tarea_detalle", tarea_id=tarea_id) + "#horas")


# ---------------------------------------------------------------------------
# Páginas de error
# ---------------------------------------------------------------------------
MENSAJES_ERROR = {
    400: "Petición no válida (el formulario caducó, vuelve a intentarlo).",
    403: "No tienes permiso para acceder a esta página.",
    404: "Página no encontrada.",
}


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def pagina_error(error):
    return render_template("error.html", codigo=error.code, mensaje=MENSAJES_ERROR[error.code]), error.code


if __name__ == "__main__":
    
    app.run(host="0.0.0.0", port=5000, debug=True)
