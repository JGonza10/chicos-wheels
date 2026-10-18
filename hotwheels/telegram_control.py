# -*- coding: utf-8 -*-
"""
Decidir desde Telegram: los avisos del monitor traen los botones
"Comprar con el bot" / "Ignorar". Este modulo (un hilo dentro del panel)
escucha esos toques con getUpdates -- solo saliente, sin abrir ningun puerto.

Seguridad, en este orden:
  1. Solo cuenta lo que llega del chat personal (TELEGRAM_CHAT_ID) y de tu
     propio usuario; cualquier otro toque se ignora en silencio.
  2. "Comprar" NUNCA compra a la primera: pide una confirmacion ("Si, comprar")
     y esa confirmacion caduca a los 10 minutos.
  3. Al arrancar se descarta todo lo acumulado: un boton pulsado mientras el
     panel estaba apagado no se ejecuta minutos u horas despues.
  4. Si la compra pasa tu tope de gasto, la confirmacion lo dice y pide el
     boton "Comprar de todos modos".

Las acciones reales (comprar, ignorar...) las inyecta dashboard_bot.py; asi
este archivo se prueba sin Telegram real (ver prueba_habilidades.py).
"""

import threading
import time

import requests

CADUCA_CONFIRMACION_SEG = 10 * 60


class Control:
    def __init__(self, token, chat_id, acciones, llamar=None, log=print):
        self.token = token
        self.chat_id = int(chat_id)
        self.acciones = acciones            # obtener / evaluar / comprar / ignorar
        self._llamar = llamar or self._llamar_telegram
        self.log = log
        self.offset = None
        self._parar = threading.Event()

    # --- Telegram ---------------------------------------------------------
    def _llamar_telegram(self, metodo, **params):
        params = {k: v for k, v in params.items() if v is not None}
        r = requests.post("https://api.telegram.org/bot%s/%s" % (self.token, metodo),
                          json=params, timeout=params.get("timeout", 0) + 15)
        return r.json()

    def _api(self, metodo, **params):
        try:
            return self._llamar(metodo, **params)
        except Exception as e:
            self.log("  [telegram_control] %s fallo: %s" % (metodo, e))
            return {"ok": False}

    # --- Logica de los botones -------------------------------------------
    def _es_mio(self, cq):
        chat = ((cq.get("message") or {}).get("chat") or {}).get("id")
        usuario = (cq.get("from") or {}).get("id")
        return chat == self.chat_id and usuario == self.chat_id

    def procesar(self, update, ahora=None):
        """Atiende UN update de Telegram. Devuelve un texto corto de lo que hizo
        (para las pruebas) o None si lo ignoro."""
        cq = update.get("callback_query")
        if not cq or not self._es_mio(cq):
            return None
        datos = cq.get("data") or ""
        partes = datos.split(":")
        accion = partes[0]
        try:
            hid = int(partes[1])
        except (IndexError, ValueError):
            self._api("answerCallbackQuery", callback_query_id=cq["id"])
            return None
        if accion == "rc":
            # Pieza que encontro el monitor de relevo (Railway): se trae al
            # panel local y sigue el camino de siempre (confirmar y comprar).
            importar = self.acciones.get("importar_relevo")
            hid = importar(hid) if importar else None
            if not hid:
                self._api("answerCallbackQuery", callback_query_id=cq["id"],
                          text="No pude traer esa pieza de Railway.", show_alert=True)
                return "relevo_fallo"
            accion = "c"
        pieza = self.acciones["obtener"](hid)
        if pieza is None:
            self._api("answerCallbackQuery", callback_query_id=cq["id"],
                      text="Esa pieza ya no existe en el panel.", show_alert=True)
            return "inexistente"

        titulo = pieza.get("titulo") or pieza.get("url")

        if accion == "i":                                   # Ignorar
            self.acciones["ignorar"](hid)
            self._api("answerCallbackQuery", callback_query_id=cq["id"], text="Ignorada ✔")
            return "ignorada"

        if accion == "x":                                   # Cancelar confirmacion
            self._api("answerCallbackQuery", callback_query_id=cq["id"], text="Cancelado")
            return "cancelada"

        if accion == "c":                                   # Pedir confirmacion
            if not pieza.get("disponible"):
                self._api("answerCallbackQuery", callback_query_id=cq["id"],
                          text="Ya está agotada.", show_alert=True)
                return "agotada"
            # Mientras confirmas, el navegador ya abre la pieza (navegador.py).
            precalentar = self.acciones.get("precalentar")
            if precalentar and pieza.get("url"):
                precalentar(pieza["url"])
            precio = pieza.get("precio_mxn")
            texto = "¿Comprar esta pieza?\n%s\nPrecio: %s × 1" % (
                titulo, ("$%s MXN" % format(precio, ",.0f")) if precio else "sin precio")
            self._api("answerCallbackQuery", callback_query_id=cq["id"], text="Confirma abajo")
            self._api("sendMessage", chat_id=self.chat_id, text=texto,
                      reply_markup={"inline_keyboard": [[
                          {"text": "✅ Sí, comprar", "callback_data": "cc:%d:n" % hid},
                          {"text": "Cancelar", "callback_data": "x:%d" % hid}]]})
            return "confirmacion_pedida"

        if accion == "cc":                                  # Confirmacion recibida
            fecha = (cq.get("message") or {}).get("date")
            ahora = ahora if ahora is not None else time.time()
            if fecha and ahora - fecha > CADUCA_CONFIRMACION_SEG:
                self._api("answerCallbackQuery", callback_query_id=cq["id"],
                          text="Esa confirmación caducó. Pulsa Comprar otra vez.", show_alert=True)
                return "caducada"
            forzar = len(partes) > 2 and partes[2] == "f"
            r = self.acciones["comprar"](hid, 1, forzar)
            if r.get("ok"):
                texto = ("Quedó en la cola (sigue otra compra en curso)." if r.get("en_cola")
                         else "🛒 Comprando… te aviso el resultado por aquí.")
            else:
                texto = "No se pudo comprar: " + (r.get("error") or "error desconocido")
            self._api("answerCallbackQuery", callback_query_id=cq["id"], text=texto[:180])
            self._api("sendMessage", chat_id=self.chat_id, text="%s\n%s" % (titulo, texto))
            return "comprando" if r.get("ok") else "rechazada"

        self._api("answerCallbackQuery", callback_query_id=cq["id"])
        return None

    # --- Bucle ---------------------------------------------------------------
    def _descartar_pendientes(self):
        r = self._api("getUpdates", offset=-1, timeout=0)
        for u in (r.get("result") or []):
            self.offset = u["update_id"] + 1

    def bucle(self):
        self._descartar_pendientes()
        espera_error = 5
        while not self._parar.is_set():
            r = self._api("getUpdates", offset=self.offset, timeout=25,
                          allowed_updates=["callback_query"])
            if not r.get("ok"):
                # 409 = otro programa consulta el mismo bot; red caida, etc.
                self._parar.wait(espera_error)
                espera_error = min(espera_error * 2, 120)
                continue
            espera_error = 5
            for u in (r.get("result") or []):
                self.offset = u["update_id"] + 1
                try:
                    self.procesar(u)
                except Exception as e:
                    self.log("  [telegram_control] error atendiendo un toque: %s" % e)

    def iniciar_hilo(self):
        hilo = threading.Thread(target=self.bucle, name="telegram_control", daemon=True)
        hilo.start()
        return hilo

    def parar(self):
        self._parar.set()
