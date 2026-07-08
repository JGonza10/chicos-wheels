"""
Inicio de sesión con Google y Facebook.

Usa Authlib para el flujo OAuth2. El usuario entra con su cuenta social,
si su correo ya existe en la tabla usuarios se reutiliza esa cuenta;
si no existe, se crea automáticamente con rol "cliente".

Requiere en Railway:
- GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET   (console.cloud.google.com)
- FACEBOOK_CLIENT_ID / FACEBOOK_CLIENT_SECRET  (developers.facebook.com)
"""
import os
import secrets
from authlib.integrations.flask_client import OAuth
from flask import Blueprint, redirect, session, url_for, jsonify

from models import db, Usuario

social_bp = Blueprint("social", __name__, url_prefix="/api/auth/social")
oauth = OAuth()


def init_oauth(app):
    oauth.init_app(app)

    oauth.register(
        name="google",
        client_id=os.environ.get("GOOGLE_CLIENT_ID"),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

    oauth.register(
        name="facebook",
        client_id=os.environ.get("FACEBOOK_CLIENT_ID"),
        client_secret=os.environ.get("FACEBOOK_CLIENT_SECRET"),
        access_token_url="https://graph.facebook.com/oauth/access_token",
        authorize_url="https://www.facebook.com/dialog/oauth",
        api_base_url="https://graph.facebook.com/",
        client_kwargs={"scope": "email public_profile"},
    )


def _iniciar_sesion_o_crear(nombre: str, email: str) -> Usuario:
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario:
        usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=secrets.token_hex(32),  # no se usa para login social, pero el campo es obligatorio
            rol="cliente",
        )
        db.session.add(usuario)
        db.session.commit()

    session["usuario_id"] = usuario.id
    return usuario


@social_bp.route("/google")
def login_google():
    redirect_uri = url_for("social.callback_google", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@social_bp.route("/google/callback")
def callback_google():
    token = oauth.google.authorize_access_token()
    perfil = token.get("userinfo", {})
    usuario = _iniciar_sesion_o_crear(perfil.get("name", "Cliente"), perfil["email"])
    return redirect(os.environ.get("FRONTEND_URL", "/"))


@social_bp.route("/facebook")
def login_facebook():
    redirect_uri = url_for("social.callback_facebook", _external=True)
    return oauth.facebook.authorize_redirect(redirect_uri)


@social_bp.route("/facebook/callback")
def callback_facebook():
    oauth.facebook.authorize_access_token()
    perfil = oauth.facebook.get("me?fields=name,email").json()
    if "email" not in perfil:
        return jsonify({"error": "Facebook no proporcionó un correo. Intenta con Google."}), 400

    usuario = _iniciar_sesion_o_crear(perfil.get("name", "Cliente"), perfil["email"])
    return redirect(os.environ.get("FRONTEND_URL", "/"))
