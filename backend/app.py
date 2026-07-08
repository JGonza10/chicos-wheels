import os
from flask import Flask
from flask_cors import CORS

from models import db
from auth import auth_bp
from routes.catalogo import catalogo_bp


def create_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["DATABASE_URL"].replace(
        "postgres://", "postgresql://", 1
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")

    db.init_app(app)
    CORS(app, supports_credentials=True, origins=os.environ.get("FRONTEND_URL", "*"))

    app.register_blueprint(auth_bp)
    app.register_blueprint(catalogo_bp)

    with app.app_context():
        db.create_all()

    @app.route("/api/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
