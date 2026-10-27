from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional

from ..extensions import db
from ..models import Role
from ..validators import strong_password, unique_email


class UserForm(FlaskForm):
    """Formulario de alta/edición. En edición la contraseña es opcional."""

    full_name = StringField("Nombre completo", validators=[DataRequired(), Length(min=3, max=120)])
    email = EmailField("Correo", validators=[DataRequired(), Email(), Length(max=120)])
    role_id = SelectField("Rol", coerce=int, validators=[DataRequired()])
    active = BooleanField("Activo", default=True)
    password = PasswordField("Contraseña", validators=[strong_password])
    confirm = PasswordField("Confirmar contraseña", validators=[EqualTo("password", message="Las contraseñas no coinciden.")])
    submit = SubmitField("Guardar")

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        self.role_id.choices = [(r.id, r.label) for r in db.session.scalars(db.select(Role).order_by(Role.id))]
        self.password.validators = (
            [Optional(), strong_password] if user else [DataRequired(), strong_password]
        )

    def validate_email(self, field):
        unique_email(self._user.id if self._user else None)(self, field)


class DeleteForm(FlaskForm):
    """Formulario vacío: solo aporta el token CSRF a las acciones POST."""

    submit = SubmitField("Eliminar")
