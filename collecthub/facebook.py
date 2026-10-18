"""
Publicar una pieza en la página de Facebook de Erik G (Graph API).

Necesita en Railway (nunca en el código):
    FB_PAGE_ID     id numérico de la página
    FB_PAGE_TOKEN  token de acceso DE PÁGINA, con pages_manage_posts
    FB_GRAPH_VERSION  opcional (por defecto v21.0)

Solo páginas: Facebook quitó en 2024 la publicación en grupos desde apps.
La foto va en este orden: la propia (1080×1080, igual que "📸 Foto lista"),
si no, la URL pública (las de Mattel/Shopify), y si no hay, solo texto.
"""
import logging
import os

import requests

log = logging.getLogger(__name__)
TIMEOUT = 30


class ErrorFacebook(Exception):
    """Mensaje ya apto para mostrarse al dueño (sin token ni detalles internos)."""


def configurado() -> bool:
    return bool(os.environ.get("FB_PAGE_ID") and os.environ.get("FB_PAGE_TOKEN"))


def _base() -> str:
    version = os.environ.get("FB_GRAPH_VERSION", "v21.0").strip() or "v21.0"
    return f"https://graph.facebook.com/{version}/{os.environ['FB_PAGE_ID'].strip()}"


def publicar(texto: str, foto_jpg: bytes | None = None, foto_url: str | None = None,
             llamar=None) -> str:
    """Publica y devuelve el id del post. Lanza ErrorFacebook si no se pudo."""
    llamar = llamar or requests.post
    if not configurado():
        raise ErrorFacebook("Falta conectar tu página: pon FB_PAGE_ID y FB_PAGE_TOKEN en Railway.")
    token = os.environ["FB_PAGE_TOKEN"].strip()
    datos = {"access_token": token}
    try:
        if foto_jpg:
            r = llamar(_base() + "/photos", data={**datos, "caption": texto},
                       files={"source": ("pieza.jpg", foto_jpg, "image/jpeg")}, timeout=TIMEOUT)
        elif foto_url:
            r = llamar(_base() + "/photos", data={**datos, "caption": texto, "url": foto_url},
                       timeout=TIMEOUT)
        else:
            r = llamar(_base() + "/feed", data={**datos, "message": texto}, timeout=TIMEOUT)
    except requests.RequestException as e:
        log.warning("Facebook no respondió: %s", type(e).__name__)
        raise ErrorFacebook("Facebook no respondió. Intenta de nuevo en un momento.")
    try:
        cuerpo = r.json()
    except ValueError:
        cuerpo = {}
    if r.status_code >= 400 or "error" in cuerpo:
        err = cuerpo.get("error") or {}
        log.warning("Facebook rechazó la publicación: %s %s", err.get("code"), err.get("message"))
        if err.get("code") in (190, 102):
            raise ErrorFacebook("El token de tu página venció o no es válido: genera uno nuevo y "
                                "actualiza FB_PAGE_TOKEN en Railway.")
        if err.get("code") in (10, 200) or "permission" in str(err.get("message", "")).lower():
            raise ErrorFacebook("Al token le falta el permiso para publicar (pages_manage_posts).")
        raise ErrorFacebook("Facebook no aceptó la publicación"
                            + (f" (código {err['code']})" if err.get("code") else "") + ".")
    post = cuerpo.get("post_id") or cuerpo.get("id")
    if not post:
        raise ErrorFacebook("Facebook no confirmó la publicación.")
    return str(post)


def link_post(post_id: str) -> str:
    return f"https://www.facebook.com/{post_id}"
