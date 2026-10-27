from app.extensions import db
from app.models import User


def get_user(email):
    return db.session.scalar(db.select(User).filter_by(email=email))


def test_register_creates_client(client):
    resp = client.post(
        "/auth/registro",
        data={"full_name": "Nuevo Cliente", "email": "Nuevo@Demo.com", "password": "Segura123!", "confirm": "Segura123!"},
    )
    assert resp.status_code == 302
    user = get_user("nuevo@demo.com")
    assert user is not None and user.role.name == "client"


def test_register_rejects_weak_password(client):
    resp = client.post(
        "/auth/registro",
        data={"full_name": "Débil", "email": "debil@demo.com", "password": "abc", "confirm": "abc"},
    )
    assert resp.status_code == 200
    assert "La contraseña debe tener".encode() in resp.data
    assert get_user("debil@demo.com") is None


def test_register_rejects_duplicate_email_case_insensitive(client):
    resp = client.post(
        "/auth/registro",
        data={"full_name": "Copia", "email": "ADMIN@demo.com", "password": "Segura123!", "confirm": "Segura123!"},
    )
    assert "Ya existe un usuario con ese correo".encode() in resp.data


def test_login_and_logout(client, login):
    assert login("admin@demo.com").headers["Location"] == "/panel"
    assert client.get("/panel").status_code == 200
    client.post("/auth/logout")
    assert client.get("/panel").status_code == 302


def test_login_wrong_password(client, login):
    resp = login("admin@demo.com", "Incorrecta1!")
    assert resp.status_code == 200
    assert client.get("/panel").status_code == 302


def test_inactive_user_cannot_login(client, login):
    resp = login("inactivo@demo.com")
    assert "inactiva".encode() in resp.data
    assert client.get("/panel").status_code == 302


def test_login_ignores_external_next(client):
    resp = client.post(
        "/auth/login?next=https://evil.com", data={"email": "admin@demo.com", "password": "Demo1234!"}
    )
    assert resp.headers["Location"] == "/panel"


def test_password_reset_flow(app, client, login):
    user = get_user("dev@demo.com")
    token = user.get_reset_token()

    resp = client.post(f"/auth/restablecer/{token}", data={"password": "NuevaClave9$", "confirm": "NuevaClave9$"})
    assert resp.status_code == 302
    assert login("dev@demo.com", "NuevaClave9$").headers["Location"] == "/panel"

    # El token es de un solo uso: tras cambiar la contraseña deja de valer.
    resp = client.get(f"/auth/restablecer/{token}")
    assert resp.headers["Location"].endswith("/auth/recuperar")


def test_invalid_reset_token(client):
    resp = client.get("/auth/restablecer/token-falso")
    assert resp.headers["Location"].endswith("/auth/recuperar")


def test_forgot_password_does_not_reveal_accounts(client):
    a = client.post("/auth/recuperar", data={"email": "admin@demo.com"}, follow_redirects=True)
    b = client.post("/auth/recuperar", data={"email": "noexiste@demo.com"}, follow_redirects=True)
    assert "Si el correo está registrado".encode() in a.data
    assert "Si el correo está registrado".encode() in b.data
