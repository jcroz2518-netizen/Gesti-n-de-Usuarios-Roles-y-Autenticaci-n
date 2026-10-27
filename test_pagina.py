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
