import pytest

# (correo, {ruta: código esperado})
MATRIX = [
    ("admin@demo.com", {"/proyectos": 200, "/tareas": 200, "/informes": 200, "/usuarios/": 200}),
    ("dev@demo.com", {"/proyectos": 403, "/tareas": 200, "/informes": 200, "/usuarios/": 403}),
    ("cliente@demo.com", {"/proyectos": 403, "/tareas": 403, "/informes": 200, "/usuarios/": 403}),
]


@pytest.mark.parametrize("email,expected", MATRIX)
def test_role_access_matrix(client, login, email, expected):
    login(email)
    for path, code in expected.items():
        assert client.get(path).status_code == code, f"{email} -> {path}"


@pytest.mark.parametrize("path", ["/panel", "/proyectos", "/tareas", "/informes", "/usuarios/"])
def test_anonymous_is_redirected_to_login(client, path):
    resp = client.get(path)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["Location"]


def test_deactivated_user_loses_session(client, login, app):
    from app.extensions import db
    from app.models import User

    login("dev@demo.com")
    assert client.get("/tareas").status_code == 200
    user = db.session.scalar(db.select(User).filter_by(email="dev@demo.com"))
    user.active = False
    db.session.commit()
    assert client.get("/tareas").status_code == 302
