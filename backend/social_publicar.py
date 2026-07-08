"""
Publicación automática de ofertas nuevas en Facebook e Instagram.

Cuando el administrador crea una oferta destacada, esta función publica
un post en la página de Facebook y en la cuenta de Instagram de negocio
usando la Meta Graph API. Se llama desde routes/catalogo.py al crear
una Oferta.

Requiere en Railway:
- META_PAGE_ACCESS_TOKEN  (token de página de Facebook, larga duración)
- META_PAGE_ID            (id numérico de la página de Facebook)
- META_IG_BUSINESS_ID     (id de la cuenta de Instagram de negocio vinculada)

Cómo se consiguen: se crea una app en developers.facebook.com, se vincula
la página de Facebook y la cuenta de Instagram de negocio, y se genera un
token de página de larga duración desde el Graph API Explorer.

Si estas variables no están configuradas, la publicación simplemente se
omite (no rompe la creación de la oferta).
"""
import os
import requests

GRAPH_URL = "https://graph.facebook.com/v19.0"


def _configurado() -> bool:
    return all(os.environ.get(v) for v in
               ("META_PAGE_ACCESS_TOKEN", "META_PAGE_ID", "META_IG_BUSINESS_ID"))


def publicar_oferta(titulo: str, descripcion: str, imagen_url: str, link_producto: str):
    """Publica la oferta en Facebook e Instagram. No lanza excepción si falla."""
    if not _configurado():
        return {"publicado": False, "motivo": "credenciales de Meta no configuradas"}

    token = os.environ["META_PAGE_ACCESS_TOKEN"]
    mensaje = f"{titulo}\n{descripcion}\n{link_producto}"

    resultado = {"facebook": None, "instagram": None}

    # --- Facebook: publicación con foto en la página ---
    try:
        pagina_id = os.environ["META_PAGE_ID"]
        resp = requests.post(
            f"{GRAPH_URL}/{pagina_id}/photos",
            data={"url": imagen_url, "caption": mensaje, "access_token": token},
            timeout=10,
        )
        resultado["facebook"] = resp.json()
    except requests.RequestException as error:
        resultado["facebook"] = {"error": str(error)}

    # --- Instagram: crear contenedor de medio y luego publicarlo ---
    try:
        ig_id = os.environ["META_IG_BUSINESS_ID"]
        contenedor = requests.post(
            f"{GRAPH_URL}/{ig_id}/media",
            data={"image_url": imagen_url, "caption": mensaje, "access_token": token},
            timeout=10,
        ).json()

        if "id" in contenedor:
            publicacion = requests.post(
                f"{GRAPH_URL}/{ig_id}/media_publish",
                data={"creation_id": contenedor["id"], "access_token": token},
                timeout=10,
            ).json()
            resultado["instagram"] = publicacion
        else:
            resultado["instagram"] = contenedor
    except requests.RequestException as error:
        resultado["instagram"] = {"error": str(error)}

    return {"publicado": True, "detalle": resultado}
