from flask import render_template


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors.html", code=403, message="No tienes permiso para acceder a esta página."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors.html", code=404, message="Página no encontrada."), 404
