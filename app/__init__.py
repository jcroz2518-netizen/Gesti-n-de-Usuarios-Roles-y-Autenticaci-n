from flask import Flask

from config import Config

from .extensions import csrf, db, login_manager, mail, migrate


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)
    login_manager.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    from . import models  # noqa: F401  (registra los modelos para Alembic)
    from .auth.routes import bp as auth_bp
    from .main.routes import bp as main_bp
    from .users.routes import bp as users_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(users_bp, url_prefix="/usuarios")

    from .errors import register_error_handlers
    from .seeds import register_commands

    register_error_handlers(app)
    register_commands(app)

    return app
