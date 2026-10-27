import pytest

from app.extensions import db
from app.models import Role, User


def get_user(email):
    return db.session.scalar(db.select(User).filter_by(email=email))


def role_id(name):
    return db.session.scalar(db.select(Role.id).filter_by(name=name))


@pytest.fixture
def admin(login):
    login("admin@demo.com")
    return get_user("admin@demo.com")


def test_list_and_filter(client, admin):
    resp = client.get("/usuarios/?estado=inactivo")
    assert b"inactivo@demo.com" in resp.data
    assert b"cliente@demo.com" not in resp.data

    resp = client.get("/usuarios/?q=Diego")
    assert b"dev@demo.com" in resp.data
    assert b"dev2@demo.com" not in resp.data


def test_create_user(client, admin):
    resp = client.post(
        "/usuarios/nuevo",
        data={
            "full_name": "Marta Dev",
            "email": "marta@demo.com",
            "role_id": role_id("developer"),
            "active": "y",
            "password": "Marta123!",
            "confirm": "Marta123!",
        },
    )
    assert resp.status_code == 302
    user = get_user("marta@demo.com")
    assert user.role.name == "developer" and user.active


def test_create_requires_password_and_unique_email(client, admin):
    resp = client.post(
        "/usuarios/nuevo",
        data={"full_name": "Repetido", "email": "dev@demo.com", "role_id": role_id("client"), "password": "", "confirm": ""},
    )
    assert resp.status_code == 200
    assert "Ya existe un usuario con ese correo".encode() in resp.data


def test_edit_user_keeps_password_when_blank(client, admin):
    user = get_user("cliente@demo.com")
    old_hash = user.password_hash
    resp = client.post(
        f"/usuarios/{user.id}/editar",
        data={"full_name": "Carla Editada", "email": "cliente@demo.com", "role_id": role_id("developer"), "active": "y"},
    )
    assert resp.status_code == 302
    db.session.refresh(user)
    assert user.full_name == "Carla Editada"
    assert user.role.name == "developer"
    assert user.password_hash == old_hash


def test_toggle_and_delete(client, admin):
    user = get_user("dev2@demo.com")
    client.post(f"/usuarios/{user.id}/estado")
    db.session.refresh(user)
    assert user.active is False

    client.post(f"/usuarios/{user.id}/eliminar")
    assert get_user("dev2@demo.com") is None


def test_admin_cannot_deactivate_or_delete_self(client, admin):
    client.post(f"/usuarios/{admin.id}/estado")
    client.post(f"/usuarios/{admin.id}/eliminar")
    db.session.refresh(admin)
    assert admin.active is True


def test_non_admin_cannot_modify_users(client, login):
    login("dev@demo.com")
    target = get_user("cliente@demo.com")
    assert client.post(f"/usuarios/{target.id}/eliminar").status_code == 403
    assert get_user("cliente@demo.com") is not None
