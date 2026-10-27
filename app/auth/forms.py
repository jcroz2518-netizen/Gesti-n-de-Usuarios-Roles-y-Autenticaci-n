from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length

from ..validators import strong_password, unique_email


class RegisterForm(FlaskForm):
    full_name = StringField("Nombre completo", validators=[DataRequired(), Length(min=3, max=120)])
    email = EmailField("Correo", validators=[DataRequired(), Email(), Length(max=120), unique_email()])
    password = PasswordField("Contraseña", validators=[DataRequired(), strong_password])
    confirm = PasswordField(
        "Confirmar contraseña",
        validators=[DataRequired(), EqualTo("password", message="Las contraseñas no coinciden.")],
    )
    submit = SubmitField("Crear cuenta")


class LoginForm(FlaskForm):
    email = EmailField("Correo", validators=[DataRequired(), Email()])
    password = PasswordField("Contraseña", validators=[DataRequired()])
    remember = BooleanField("Recordarme")
    submit = SubmitField("Entrar")


class ForgotPasswordForm(FlaskForm):
    email = EmailField("Correo", validators=[DataRequired(), Email()])
    submit = SubmitField("Enviar enlace")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("Nueva contraseña", validators=[DataRequired(), strong_password])
    confirm = PasswordField(
        "Confirmar contraseña",
        validators=[DataRequired(), EqualTo("password", message="Las contraseñas no coinciden.")],
    )
    submit = SubmitField("Cambiar contraseña")
