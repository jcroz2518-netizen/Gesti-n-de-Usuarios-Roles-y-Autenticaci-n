"""Pruebas automáticas. Ejecutar con:  pytest"""
import os
import tempfile

# La base de datos de pruebas va a una carpeta temporal, nunca a usuarios.db
os.environ["BASE_DATOS"] = os.path.join(tempfile.mkdtemp(), "importacion.db")

import pytest  # noqa: E402

import base_datos  # noqa: E402
import pagina  # noqa: E402

CONTRASENA = base_datos.CONTRASENA_PRUEBA


@pytest.fixture
def app(tmp_path):
    ruta = str(tmp_path / "pruebas.db")
    base_datos.inicializar(ruta, con_datos=True)
    pagina.app.config.update(BASE_DATOS=ruta, CSRF_ACTIVO=False, TESTING=True)
    with pagina.app.app_context():
        yield pagina.app


@pytest.fixture
def cliente(app):
    return app.test_client()


@pytest.fixture
def entrar(cliente):
    def _entrar(correo, contrasena=CONTRASENA):
        return cliente.post("/login", data={"correo": correo, "contrasena": contrasena})

    return _entrar


def usuario(correo):
    return base_datos.buscar_usuario_por_correo(correo)


def id_rol(nombre):
    return next(r["id"] for r in base_datos.listar_roles() if r["nombre"] == nombre)


# --- Migraciones y datos de prueba ------------------------------------------
def test_migraciones_y_seeders_son_idempotentes(tmp_path):
    ruta = str(tmp_path / "doble.db")
    base_datos.inicializar(ruta, con_datos=True)
    base_datos.inicializar(ruta, con_datos=True)
    conexion = base_datos.abrir(ruta)
    assert conexion.execute("PRAGMA user_version").fetchone()[0] == len(base_datos.MIGRACIONES)
    assert conexion.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 3
    assert conexion.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == len(base_datos.USUARIOS_PRUEBA)
    conexion.close()


# --- Autenticación -----------------------------------------------------------
def test_registro_crea_cliente(cliente):
    datos = {"nombre": "Nuevo Cliente", "correo": "Nuevo@Demo.com", "contrasena": "Segura123!", "confirmacion": "Segura123!"}
    assert cliente.post("/registro", data=datos).status_code == 302
    assert usuario("nuevo@demo.com")["rol"] == "cliente"


def test_registro_rechaza_contrasena_debil(cliente):
    datos = {"nombre": "Débil", "correo": "debil@demo.com", "contrasena": "abc", "confirmacion": "abc"}
    respuesta = cliente.post("/registro", data=datos)
    assert "La contraseña debe tener".encode() in respuesta.data
    assert usuario("debil@demo.com") is None


def test_registro_rechaza_correo_repetido_sin_importar_mayusculas(cliente):
    datos = {"nombre": "Copia", "correo": "ADMIN@demo.com", "contrasena": "Segura123!", "confirmacion": "Segura123!"}
    assert "Ya existe un usuario con ese correo".encode() in cliente.post("/registro", data=datos).data


def test_registro_rechaza_confirmacion_distinta(cliente):
    datos = {"nombre": "Otro", "correo": "otro@demo.com", "contrasena": "Segura123!", "confirmacion": "Otra123!"}
    assert "no coinciden".encode() in cliente.post("/registro", data=datos).data


def test_login_y_logout(cliente, entrar):
    assert entrar("admin@demo.com").headers["Location"] == "/panel"
    assert cliente.get("/panel").status_code == 200
    cliente.post("/logout")
    assert cliente.get("/panel").status_code == 302


def test_login_contrasena_incorrecta(cliente, entrar):
    assert entrar("admin@demo.com", "Incorrecta1!").status_code == 200
    assert cliente.get("/panel").status_code == 302


def test_usuario_inactivo_no_entra(cliente, entrar):
    assert "inactiva".encode() in entrar("inactivo@demo.com").data
    assert cliente.get("/panel").status_code == 302


def test_login_ignora_next_externo(cliente):
    respuesta = cliente.post("/login?next=https://malo.com", data={"correo": "admin@demo.com", "contrasena": CONTRASENA})
    assert respuesta.headers["Location"] == "/panel"


def test_recuperar_contrasena(cliente, entrar):
    token = pagina.generar_token(usuario("dev@demo.com"))
    respuesta = cliente.post(f"/restablecer/{token}", data={"contrasena": "NuevaClave9$", "confirmacion": "NuevaClave9$"})
    assert respuesta.status_code == 302
    assert entrar("dev@demo.com", "NuevaClave9$").headers["Location"] == "/panel"
    # El enlace es de un solo uso
    assert cliente.get(f"/restablecer/{token}").headers["Location"].endswith("/recuperar")


def test_token_falso(cliente):
    assert cliente.get("/restablecer/token-falso").headers["Location"].endswith("/recuperar")


def test_recuperar_no_revela_cuentas(cliente):
    a = cliente.post("/recuperar", data={"correo": "admin@demo.com"}, follow_redirects=True)
    b = cliente.post("/recuperar", data={"correo": "noexiste@demo.com"}, follow_redirects=True)
    assert "Si el correo está registrado".encode() in a.data
    assert "Si el correo está registrado".encode() in b.data


def test_csrf_bloquea_post_sin_token(app, cliente):
    app.config["CSRF_ACTIVO"] = True
    respuesta = cliente.post("/login", data={"correo": "admin@demo.com", "contrasena": CONTRASENA})
    assert respuesta.status_code == 400


# --- Control de acceso por rol -----------------------------------------------
MATRIZ = [
    ("admin@demo.com", {"/proyectos": 200, "/tareas": 200, "/informes": 200, "/usuarios": 200}),
    ("dev@demo.com", {"/proyectos": 403, "/tareas": 200, "/informes": 200, "/usuarios": 403}),
    ("cliente@demo.com", {"/proyectos": 403, "/tareas": 403, "/informes": 200, "/usuarios": 403}),
]


@pytest.mark.parametrize("correo,esperado", MATRIZ)
def test_matriz_de_acceso(cliente, entrar, correo, esperado):
    entrar(correo)
    for ruta, codigo in esperado.items():
        assert cliente.get(ruta).status_code == codigo, f"{correo} -> {ruta}"


@pytest.mark.parametrize("ruta", ["/panel", "/proyectos", "/tareas", "/informes", "/usuarios"])
def test_anonimo_va_al_login(cliente, ruta):
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


def test_usuario_desactivado_pierde_la_sesion(cliente, entrar):
    entrar("dev@demo.com")
    assert cliente.get("/tareas").status_code == 200
    base_datos.cambiar_estado(usuario("dev@demo.com")["id"])
    assert cliente.get("/tareas").status_code == 302


# --- CRUD de usuarios --------------------------------------------------------
@pytest.fixture
def admin(entrar):
    entrar("admin@demo.com")
    return usuario("admin@demo.com")


def test_listar_y_filtrar(cliente, admin):
    respuesta = cliente.get("/usuarios?estado=inactivo")
    assert b"inactivo@demo.com" in respuesta.data and b"cliente@demo.com" not in respuesta.data
    respuesta = cliente.get("/usuarios?q=Diego")
    assert b"dev@demo.com" in respuesta.data and b"dev2@demo.com" not in respuesta.data


def test_crear_usuario(cliente, admin):
    datos = {"nombre": "Marta Dev", "correo": "marta@demo.com", "rol_id": id_rol("desarrollador"),
             "activo": "1", "contrasena": "Marta123!", "confirmacion": "Marta123!"}
    assert cliente.post("/usuarios/nuevo", data=datos).status_code == 302
    marta = usuario("marta@demo.com")
    assert marta["rol"] == "desarrollador" and marta["activo"] == 1


def test_crear_valida_correo_unico_y_contrasena(cliente, admin):
    datos = {"nombre": "Repetido", "correo": "dev@demo.com", "rol_id": id_rol("cliente"), "contrasena": ""}
    respuesta = cliente.post("/usuarios/nuevo", data=datos)
    assert "Ya existe un usuario con ese correo".encode() in respuesta.data
    assert "La contraseña es obligatoria".encode() in respuesta.data


def test_editar_sin_cambiar_contrasena(cliente, admin):
    carla = usuario("cliente@demo.com")
    datos = {"nombre": "Carla Editada", "correo": "cliente@demo.com", "rol_id": id_rol("desarrollador"), "activo": "1"}
    assert cliente.post(f"/usuarios/{carla['id']}/editar", data=datos).status_code == 302
    editada = usuario("cliente@demo.com")
    assert editada["nombre"] == "Carla Editada" and editada["rol"] == "desarrollador"
    assert editada["contrasena"] == carla["contrasena"]


def test_activar_desactivar_y_eliminar(cliente, admin):
    lucia = usuario("dev2@demo.com")
    cliente.post(f"/usuarios/{lucia['id']}/estado")
    assert usuario("dev2@demo.com")["activo"] == 0
    cliente.post(f"/usuarios/{lucia['id']}/eliminar")
    assert usuario("dev2@demo.com") is None


def test_admin_no_puede_desactivarse_ni_eliminarse(cliente, admin):
    cliente.post(f"/usuarios/{admin['id']}/estado")
    cliente.post(f"/usuarios/{admin['id']}/eliminar")
    datos = {"nombre": admin["nombre"], "correo": admin["correo"], "rol_id": id_rol("cliente"), "activo": "1"}
    cliente.post(f"/usuarios/{admin['id']}/editar", data=datos)
    assert usuario("admin@demo.com")["activo"] == 1
    assert usuario("admin@demo.com")["rol"] == "admin"


def test_no_admin_no_modifica_usuarios(cliente, entrar):
    entrar("dev@demo.com")
    carla = usuario("cliente@demo.com")
    assert cliente.post(f"/usuarios/{carla['id']}/eliminar").status_code == 403
    assert usuario("cliente@demo.com") is not None


# --- Proyectos (Hito 2) ------------------------------------------------------
DATOS_PROYECTO = {"nombre": "ERP interno", "descripcion": "Sistema de gestión", "objetivos": "Unificar áreas",
                  "fecha_inicio": "2027-01-01", "fecha_fin": "2027-12-31", "presupuesto": "120000.50",
                  "estado": "planificacion"}


def proyecto(nombre):
    return next((p for p in base_datos.listar_proyectos(nombre) if p["nombre"] == nombre), None)


def test_seeders_crean_proyectos_con_equipo_y_fases(app):
    portal = proyecto("Portal de clientes")
    assert portal["estado"] == "activo"
    assert portal["num_miembros"] == 4 and portal["num_fases"] == 5 and portal["fases_completadas"] == 2


def test_detalle_muestra_equipo_y_fases(cliente, admin):
    portal = proyecto("Portal de clientes")
    respuesta = cliente.get(f"/proyectos/{portal['id']}")
    assert "Desarrollador backend".encode() in respuesta.data and b"Diego Desarrollador" in respuesta.data
    assert "Análisis de requisitos".encode() in respuesta.data and b"40 %" in respuesta.data
    assert "$ 85,000.00".encode() in respuesta.data


def test_crear_proyecto(cliente, admin):
    respuesta = cliente.post("/proyectos/nuevo", data=DATOS_PROYECTO)
    erp = proyecto("ERP interno")
    assert respuesta.headers["Location"] == f"/proyectos/{erp['id']}"
    assert erp["presupuesto"] == 120000.50 and erp["estado"] == "planificacion"
    assert b"ERP interno" in cliente.get("/proyectos").data


def test_crear_proyecto_valida_campos(cliente, admin):
    datos = dict(DATOS_PROYECTO, nombre="", fecha_fin="2026-01-01", presupuesto="-5", estado="inventado")
    respuesta = cliente.post("/proyectos/nuevo", data=datos)
    assert "El nombre es obligatorio".encode() in respuesta.data
    assert "no puede ser anterior".encode() in respuesta.data
    assert "mayor o igual a 0".encode() in respuesta.data
    assert "Selecciona un estado válido".encode() in respuesta.data
    assert len(base_datos.listar_proyectos()) == len(base_datos.PROYECTOS_PRUEBA)


def test_filtrar_proyectos_por_estado(cliente, admin):
    respuesta = cliente.get("/proyectos?estado=planificacion")
    assert "App móvil de inventario".encode() in respuesta.data
    assert "Portal de clientes".encode() not in respuesta.data


def test_editar_proyecto(cliente, admin):
    portal = proyecto("Portal de clientes")
    datos = dict(DATOS_PROYECTO, nombre="Portal de clientes", fecha_inicio=portal["fecha_inicio"],
                 fecha_fin="2027-03-31", estado="pausado")
    assert cliente.post(f"/proyectos/{portal['id']}/editar", data=datos).status_code == 302
    editado = base_datos.obtener_proyecto(portal["id"])
    assert editado["estado"] == "pausado" and editado["fecha_fin"] == "2027-03-31"


def test_editar_proyecto_no_deja_fases_fuera_de_fechas(cliente, admin):
    portal = proyecto("Portal de clientes")
    datos = dict(DATOS_PROYECTO, nombre="Portal de clientes", fecha_inicio=portal["fecha_inicio"],
                 fecha_fin="2026-12-31")
    respuesta = cliente.post(f"/proyectos/{portal['id']}/editar", data=datos)
    assert "ajústalas antes".encode() in respuesta.data
    assert base_datos.obtener_proyecto(portal["id"])["fecha_fin"] == portal["fecha_fin"]


def test_eliminar_proyecto_borra_miembros_y_fases(cliente, admin):
    portal = proyecto("Portal de clientes")
    cliente.post(f"/proyectos/{portal['id']}/eliminar")
    assert base_datos.obtener_proyecto(portal["id"]) is None
    assert base_datos.listar_miembros(portal["id"]) == [] and base_datos.listar_fases(portal["id"]) == []


def test_asignar_cambiar_rol_y_quitar_miembro(cliente, admin):
    app_movil = proyecto("App móvil de inventario")
    lucia = usuario("dev2@demo.com")
    ruta = f"/proyectos/{app_movil['id']}/miembros"
    cliente.post(ruta, data={"usuario_id": lucia["id"], "rol_proyecto": "QA / Tester"})
    cliente.post(ruta, data={"usuario_id": lucia["id"], "rol_proyecto": "Diseñador UX/UI"})
    roles = {m["correo"]: m["rol_proyecto"] for m in base_datos.listar_miembros(app_movil["id"])}
    assert roles["dev2@demo.com"] == "Diseñador UX/UI"
    cliente.post(f"{ruta}/{lucia['id']}/quitar")
    assert not base_datos.es_miembro(app_movil["id"], lucia["id"])


def test_no_asigna_inactivos_ni_roles_invalidos(cliente, admin):
    app_movil = proyecto("App móvil de inventario")
    ruta = f"/proyectos/{app_movil['id']}/miembros"
    inactivo = usuario("inactivo@demo.com")
    respuesta = cliente.post(ruta, data={"usuario_id": inactivo["id"], "rol_proyecto": "Stakeholder"},
                             follow_redirects=True)
    assert "usuarios inactivos".encode() in respuesta.data
    lucia = usuario("dev2@demo.com")
    cliente.post(ruta, data={"usuario_id": lucia["id"], "rol_proyecto": "Jefe supremo"})
    assert not base_datos.es_miembro(app_movil["id"], lucia["id"])
    assert not base_datos.es_miembro(app_movil["id"], inactivo["id"])


def test_eliminar_usuario_lo_quita_de_los_equipos(cliente, admin):
    lucia = usuario("dev2@demo.com")
    portal = proyecto("Portal de clientes")
    cliente.post(f"/usuarios/{lucia['id']}/eliminar")
    assert not base_datos.es_miembro(portal["id"], lucia["id"])


def test_crud_de_fases(cliente, admin):
    app_movil = proyecto("App móvil de inventario")
    base = f"/proyectos/{app_movil['id']}/fases"
    assert b'value="2"' in cliente.get(f"{base}/nueva").data  # siguiente orden sugerido
    datos = {"nombre": "Desarrollo", "descripcion": "Sprints 1-6", "orden": "2",
             "fecha_inicio": "2027-02-08", "fecha_fin": "2027-05-28", "estado": "pendiente"}
    assert cliente.post(f"{base}/nueva", data=datos).status_code == 302
    fase = base_datos.listar_fases(app_movil["id"])[-1]
    assert fase["nombre"] == "Desarrollo" and fase["orden"] == 2

    cliente.post(f"{base}/{fase['id']}/editar", data=dict(datos, estado="en_curso"))
    assert base_datos.obtener_fase(app_movil["id"], fase["id"])["estado"] == "en_curso"

    cliente.post(f"{base}/{fase['id']}/eliminar")
    assert base_datos.obtener_fase(app_movil["id"], fase["id"]) is None


def test_fase_debe_estar_dentro_del_proyecto(cliente, admin):
    app_movil = proyecto("App móvil de inventario")
    datos = {"nombre": "Fuera de plazo", "orden": "2", "fecha_inicio": "2027-06-01",
             "fecha_fin": "2027-08-01", "estado": "pendiente"}
    respuesta = cliente.post(f"/proyectos/{app_movil['id']}/fases/nueva", data=datos)
    assert "dentro de las fechas del proyecto".encode() in respuesta.data
    assert len(base_datos.listar_fases(app_movil["id"])) == 1


def test_fase_de_otro_proyecto_da_404(cliente, admin):
    portal, app_movil = proyecto("Portal de clientes"), proyecto("App móvil de inventario")
    fase_portal = base_datos.listar_fases(portal["id"])[0]
    assert cliente.post(f"/proyectos/{app_movil['id']}/fases/{fase_portal['id']}/eliminar").status_code == 404
    assert cliente.get("/proyectos/9999").status_code == 404


def test_no_admin_no_gestiona_proyectos(cliente, entrar):
    entrar("dev@demo.com")
    portal = proyecto("Portal de clientes")
    assert cliente.post("/proyectos/nuevo", data=DATOS_PROYECTO).status_code == 403
    assert cliente.post(f"/proyectos/{portal['id']}/eliminar").status_code == 403
    assert cliente.post(f"/proyectos/{portal['id']}/miembros",
                        data={"usuario_id": "1", "rol_proyecto": "Analista"}).status_code == 403
    assert base_datos.obtener_proyecto(portal["id"]) is not None


# --- Tareas y estimación de tiempos (Hito 3) ---------------------------------
def tarea(titulo):
    return next((t for t in base_datos.listar_tareas(titulo) if t["titulo"] == titulo), None)


def fase(nombre_proyecto, nombre_fase):
    return next(f for f in base_datos.listar_fases(proyecto(nombre_proyecto)["id"]) if f["nombre"] == nombre_fase)


def datos_tarea(**cambios):
    datos = {"titulo": "Exportar a PDF", "descripcion": "Facturas en PDF", "prioridad": "alta",
             "estado": "por_hacer", "horas_estimadas": "8",
             "fase_id": str(fase("Portal de clientes", "Desarrollo")["id"]),
             "responsable_id": str(usuario("dev2@demo.com")["id"])}
    datos.update(cambios)
    return datos


def test_seeders_crean_tareas_con_horas(app):
    assert len(base_datos.listar_tareas()) == len(base_datos.TAREAS_PRUEBA)
    api = tarea("API de autenticación")
    assert api["horas_estimadas"] == 24 and api["horas_reales"] == 18 and api["estado"] == "en_revision"
    assert tarea("Notificaciones por correo")["responsable_id"] is None


def test_lista_filtra_por_responsable_estado_y_prioridad(cliente, admin):
    lucia = usuario("dev2@demo.com")
    respuesta = cliente.get(f"/tareas?responsable={lucia['id']}")
    assert b"Pantalla de facturas" in respuesta.data and "Módulo de pedidos".encode() not in respuesta.data
    respuesta = cliente.get("/tareas?responsable=ninguno")
    assert b"Notificaciones por correo" in respuesta.data and b"Plan de pruebas" not in respuesta.data
    respuesta = cliente.get("/tareas?estado=en_revision")
    assert "API de autenticación".encode() in respuesta.data and b"Plan de pruebas" not in respuesta.data
    respuesta = cliente.get("/tareas?prioridad=critica")
    assert "API de autenticación".encode() in respuesta.data and "Módulo de pedidos".encode() not in respuesta.data


def test_tablero_kanban(cliente, admin):
    respuesta = cliente.get("/tareas?vista=kanban")
    texto = respuesta.data.decode()
    assert respuesta.status_code == 200
    assert all(columna in texto for columna in base_datos.ESTADOS_TAREA.values())
    assert 'draggable="true"' in texto and 'id="form-mover"' in texto


def test_desarrollador_solo_ve_tareas_de_sus_proyectos(cliente, entrar):
    entrar("dev2@demo.com")  # miembro del Portal, no de la App móvil
    respuesta = cliente.get("/tareas")
    assert b"Pantalla de facturas" in respuesta.data
    assert b"equipo de almac" not in respuesta.data
    ajena = tarea("Reunión con el equipo de almacén")
    assert cliente.get(f"/tareas/{ajena['id']}").status_code == 403


def test_desarrollador_no_crea_ni_edita_tareas(cliente, entrar):
    entrar("dev@demo.com")
    portal = proyecto("Portal de clientes")
    assert cliente.post(f"/tareas/nueva?proyecto={portal['id']}", data=datos_tarea()).status_code == 403
    api = tarea("API de autenticación")
    assert cliente.post(f"/tareas/{api['id']}/eliminar").status_code == 403
    assert tarea("Exportar a PDF") is None


def test_cliente_no_accede_a_tareas(cliente, entrar):
    entrar("cliente@demo.com")
    assert cliente.get(f"/tareas/{tarea('Plan de pruebas')['id']}").status_code == 403


def test_nueva_tarea_pide_primero_el_proyecto(cliente, admin):
    respuesta = cliente.get("/tareas/nueva")
    assert "¿A qué proyecto pertenece?".encode() in respuesta.data
    portal = proyecto("Portal de clientes")
    assert "Análisis de requisitos".encode() in cliente.get(f"/tareas/nueva?proyecto={portal['id']}").data


def test_crear_tarea(cliente, admin):
    portal = proyecto("Portal de clientes")
    respuesta = cliente.post(f"/tareas/nueva?proyecto={portal['id']}", data=datos_tarea())
    nueva = tarea("Exportar a PDF")
    assert respuesta.headers["Location"] == f"/tareas/{nueva['id']}"
    assert nueva["responsable_id"] == usuario("dev2@demo.com")["id"]
    assert nueva["prioridad"] == "alta" and nueva["horas_estimadas"] == 8 and nueva["fase"] == "Desarrollo"


def test_crear_tarea_valida_campos(cliente, admin):
    app_movil = proyecto("App móvil de inventario")
    datos = datos_tarea(titulo="", prioridad="urgentisima", estado="x", horas_estimadas="-1",
                        responsable_id=str(usuario("cliente@demo.com")["id"]))  # fase y cliente son de otro proyecto
    respuesta = cliente.post(f"/tareas/nueva?proyecto={app_movil['id']}", data=datos)
    texto = respuesta.data.decode()
    for mensaje in ("El título es obligatorio", "Selecciona una fase del proyecto", "Selecciona una prioridad",
                    "Selecciona un estado", "Las horas estimadas deben ser", "debe ser miembro del equipo"):
        assert mensaje in texto, mensaje
    assert tarea("") is None and len(base_datos.listar_tareas()) == len(base_datos.TAREAS_PRUEBA)


def test_no_asigna_tareas_a_inactivos(cliente, admin):
    portal = proyecto("Portal de clientes")
    base_datos.cambiar_estado(usuario("dev2@demo.com")["id"])
    respuesta = cliente.post(f"/tareas/nueva?proyecto={portal['id']}", data=datos_tarea())
    assert "usuarios inactivos".encode() in respuesta.data


def test_editar_tarea(cliente, admin):
    pedidos = tarea("Módulo de pedidos")
    datos = datos_tarea(titulo="Módulo de pedidos", estado="en_revision", horas_estimadas="48", responsable_id="")
    assert cliente.post(f"/tareas/{pedidos['id']}/editar", data=datos).status_code == 302
    editada = base_datos.obtener_tarea(pedidos["id"])
    assert editada["estado"] == "en_revision" and editada["horas_estimadas"] == 48
    assert editada["responsable_id"] is None and editada["horas_reales"] == 7  # las horas se conservan


def test_eliminar_tarea_borra_sus_horas(cliente, admin):
    api = tarea("API de autenticación")
    cliente.post(f"/tareas/{api['id']}/eliminar")
    assert base_datos.obtener_tarea(api["id"]) is None and base_datos.listar_registros(api["id"]) == []


def test_responsable_mueve_su_tarea_en_el_tablero(cliente, entrar):
    entrar("dev@demo.com")
    pedidos = tarea("Módulo de pedidos")
    respuesta = cliente.post(f"/tareas/{pedidos['id']}/estado",
                             data={"estado": "en_revision", "next": "/tareas?vista=kanban"})
    assert respuesta.headers["Location"] == "/tareas?vista=kanban"
    assert base_datos.obtener_tarea(pedidos["id"])["estado"] == "en_revision"
    # No puede mover la tarea de otra persona aunque sea del mismo proyecto
    facturas = tarea("Pantalla de facturas")
    assert cliente.post(f"/tareas/{facturas['id']}/estado", data={"estado": "concluida"}).status_code == 403
    assert base_datos.obtener_tarea(facturas["id"])["estado"] == "en_progreso"


def test_cambio_de_estado_ignora_next_externo_y_estados_invalidos(cliente, admin):
    pedidos = tarea("Módulo de pedidos")
    for externo in ("https://malo.com", "//malo.com", "/\\malo.com"):
        respuesta = cliente.post(f"/tareas/{pedidos['id']}/estado", data={"estado": "concluida", "next": externo})
        assert respuesta.headers["Location"] == f"/tareas/{pedidos['id']}"
    cliente.post(f"/tareas/{pedidos['id']}/estado", data={"estado": "inventado"})
    assert base_datos.obtener_tarea(pedidos["id"])["estado"] == "concluida"


def test_registrar_y_eliminar_horas(cliente, entrar):
    entrar("dev@demo.com")
    pedidos = tarea("Módulo de pedidos")
    respuesta = cliente.post(f"/tareas/{pedidos['id']}/horas", data={"fecha": "2026-11-12", "horas": "3.5", "nota": "CRUD"})
    assert respuesta.status_code == 302
    assert base_datos.obtener_tarea(pedidos["id"])["horas_reales"] == 10.5
    registro = base_datos.listar_registros(pedidos["id"])[0]
    assert registro["usuario_id"] == usuario("dev@demo.com")["id"] and registro["nota"] == "CRUD"
    cliente.post(f"/tareas/{pedidos['id']}/horas/{registro['id']}/eliminar")
    assert base_datos.obtener_tarea(pedidos["id"])["horas_reales"] == 7


def test_registro_de_horas_valida_datos(cliente, entrar):
    entrar("dev@demo.com")
    pedidos = tarea("Módulo de pedidos")
    for datos, mensaje in [({"fecha": "2099-01-01", "horas": "2"}, "fechas futuras"),
                           ({"fecha": "2026-11-12", "horas": "0"}, "mayor que 0"),
                           ({"fecha": "2026-11-12", "horas": "25"}, "mayor que 0"),
                           ({"fecha": "ayer", "horas": "2"}, "fecha válida")]:
        assert mensaje.encode() in cliente.post(f"/tareas/{pedidos['id']}/horas", data=datos).data, mensaje
    assert base_datos.obtener_tarea(pedidos["id"])["horas_reales"] == 7


def test_solo_el_responsable_registra_horas(cliente, entrar):
    entrar("dev@demo.com")
    facturas = tarea("Pantalla de facturas")  # de Lucía
    assert cliente.post(f"/tareas/{facturas['id']}/horas", data={"fecha": "2026-11-12", "horas": "1"}).status_code == 403
    # Tampoco puede borrar horas registradas por otra persona
    entrevistas = tarea("Entrevistas con el cliente")
    registro = base_datos.listar_registros(entrevistas["id"])[0]
    assert cliente.post(f"/tareas/{entrevistas['id']}/horas/{registro['id']}/eliminar").status_code == 403


def test_fase_con_tareas_no_se_elimina(cliente, admin):
    desarrollo = fase("Portal de clientes", "Desarrollo")
    respuesta = cliente.post(f"/proyectos/{desarrollo['proyecto_id']}/fases/{desarrollo['id']}/eliminar",
                             follow_redirects=True)
    assert "muévelas a otra fase".encode() in respuesta.data
    assert base_datos.obtener_fase(desarrollo["proyecto_id"], desarrollo["id"]) is not None


def test_quitar_miembro_deja_sus_tareas_sin_responsable(cliente, admin):
    portal, lucia = proyecto("Portal de clientes"), usuario("dev2@demo.com")
    cliente.post(f"/proyectos/{portal['id']}/miembros/{lucia['id']}/quitar")
    facturas = tarea("Pantalla de facturas")
    assert facturas["responsable_id"] is None and facturas["horas_reales"] == 6


def test_eliminar_proyecto_borra_sus_tareas(cliente, admin):
    portal = proyecto("Portal de clientes")
    cliente.post(f"/proyectos/{portal['id']}/eliminar")
    assert base_datos.listar_tareas(proyecto=portal["id"]) == []
    assert tarea("API de autenticación") is None


def test_detalle_de_proyecto_resume_horas_por_fase(cliente, admin):
    portal = proyecto("Portal de clientes")
    respuesta = cliente.get(f"/proyectos/{portal['id']}").data.decode()
    assert "118 h</span> / 208 h" in respuesta  # horas reales / estimadas del proyecto completo
    assert "Ver tablero de tareas" in respuesta


def test_detalle_de_tarea_muestra_desviacion(cliente, admin):
    diseno = tarea("Prototipo de pantallas")  # 28 h reales de 30 estimadas
    respuesta = cliente.get(f"/tareas/{diseno['id']}").data.decode()
    assert "-2 h" in respuesta and "93 %" in respuesta
