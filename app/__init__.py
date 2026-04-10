"""WITEK — Wirtualny Informator Taktyczno-Ekonomiczny Koalicji"""

from flask import Flask
from .config import Config
from .database import db, init_db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    init_db(app)

    from .routes import dashboard, players, alliances, attacks, defense, map as map_route, reports, auth
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(players.bp)
    app.register_blueprint(alliances.bp)
    app.register_blueprint(attacks.bp)
    app.register_blueprint(defense.bp)
    app.register_blueprint(map_route.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(auth.bp)

    from .routes import api_ext
    app.register_blueprint(api_ext.bp)

    @app.context_processor
    def inject_user():
        from .auth_utils import get_current_user
        return {"current_user": get_current_user()}

    return app
