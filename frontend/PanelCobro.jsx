import { useEffect, useRef, useState } from "react";
import { api } from "../api";

/**
 * Panel de cobro rápido (punto de venta).
 *
 * - Código de barras: la mayoría de lectores físicos funcionan como un
 *   teclado, así que basta con mantener el foco en el input de texto.
 * - QR: si el navegador soporta BarcodeDetector (Chrome/Edge en Android
 *   y escritorio), se activa la cámara y se lee en vivo. Si no lo soporta,
 *   se puede escribir la clave manualmente.
 * - Voz: usa la Web Speech API del navegador para transcribir lo que se
 *   dice y normaliza el texto a una clave tipo "HW-1024" antes de buscarla.
 */
export default function PanelCobro() {
  const [codigo, setCodigo] = useState("");
  const [items, setItems] = useState([]);
  const [mensaje, setMensaje] = useState("");
  const [escuchando, setEscuchando] = useState(false);
  const [camaraDisponible, setCamaraDisponible] = useState(false);
  const videoRef = useRef(null);

  useEffect(() => {
    setCamaraDisponible("BarcodeDetector" in window);
  }, []);

  const buscarYAgregar = async (codigoLeido) => {
    const limpio = codigoLeido.trim().toUpperCase();
    if (!limpio) return;

    try {
      const producto = await api.get(`/api/productos/buscar-codigo?codigo=${encodeURIComponent(limpio)}`);
      setItems((prev) => {
        const existente = prev.find((i) => i.producto_id === producto.id);
        if (existente) {
          return prev.map((i) => i.producto_id === producto.id ? { ...i, cantidad: i.cantidad + 1 } : i);
        }
        return [...prev, { producto_id: producto.id, nombre: producto.nombre, precio: producto.precio, cantidad: 1 }];
      });
      setMensaje(`Agregado: ${producto.nombre}`);
    } catch (error) {
      setMensaje(error.message);
    } finally {
      setCodigo("");
    }
  };

  const normalizarClaveHablada = (texto) => {
    // "hache doble guión mil veinticuatro" -> aproximación simple: quita espacios y pasa a mayúsculas.
    // Para un vocabulario más preciso conviene mandar directo la clave tal como se pronuncia (ej. "H W 1024").
    return texto.replace(/\s+/g, "").toUpperCase();
  };

  const escucharPorVoz = () => {
    const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Reconocimiento) {
      setMensaje("Este navegador no soporta reconocimiento de voz. Usa Chrome.");
      return;
    }

    const reconocimiento = new Reconocimiento();
    reconocimiento.lang = "es-MX";
    reconocimiento.continuous = false;

    reconocimiento.onstart = () => setEscuchando(true);
    reconocimiento.onend = () => setEscuchando(false);
    reconocimiento.onresult = (evento) => {
      const texto = evento.results[0][0].transcript;
      buscarYAgregar(normalizarClaveHablada(texto));
    };

    reconocimiento.start();
  };

  const activarCamara = async () => {
    if (!camaraDisponible) return;
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
    videoRef.current.srcObject = stream;
    await videoRef.current.play();

    const detector = new window.BarcodeDetector({ formats: ["qr_code", "ean_13", "code_128"] });
    const intervalo = setInterval(async () => {
      try {
        const resultados = await detector.detect(videoRef.current);
        if (resultados.length > 0) {
          buscarYAgregar(resultados[0].rawValue);
          clearInterval(intervalo);
          stream.getTracks().forEach((t) => t.stop());
        }
      } catch { /* el frame aún no está listo */ }
    }, 400);
  };

  const total = items.reduce((suma, i) => suma + i.precio * i.cantidad, 0);

  const cobrar = async () => {
    if (items.length === 0) return;
    try {
      const respuesta = await api.post("/api/pedidos/cobro-directo", {
        items: items.map((i) => ({ producto_id: i.producto_id, cantidad: i.cantidad })),
      });
      window.open(respuesta.link_pago, "_blank", "noopener");
      setItems([]);
    } catch (error) {
      setMensaje(error.message);
    }
  };

  return (
    <div className="contenedor" style={{ padding: "24px 20px", maxWidth: 560 }}>
      <h1 style={{ fontSize: 20 }}>Panel de cobro</h1>
      <p style={{ color: "var(--texto-secundario)", fontSize: 13 }}>
        Escanea el código de barras, el QR, o dicta la clave del producto en voz alta.
      </p>

      <form onSubmit={(e) => { e.preventDefault(); buscarYAgregar(codigo); }} style={{ display: "flex", gap: 8, margin: "16px 0" }}>
        <input
          autoFocus
          value={codigo}
          onChange={(e) => setCodigo(e.target.value)}
          placeholder="Código de barras o clave del producto"
          style={{ flex: 1, padding: 10, borderRadius: "var(--radio)", border: "1px solid var(--borde)", background: "var(--superficie)", color: "var(--texto)" }}
        />
        <button type="submit" className="boton-primario">Agregar</button>
      </form>

      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <button onClick={escucharPorVoz} className="boton-secundario" disabled={escuchando}>
          {escuchando ? "Escuchando…" : "🎙 Cobrar por voz"}
        </button>
        <button onClick={activarCamara} className="boton-secundario" disabled={!camaraDisponible}>
          📷 Escanear QR/código
        </button>
      </div>

      <video ref={videoRef} style={{ width: "100%", borderRadius: 8, display: camaraDisponible ? "block" : "none", marginBottom: 16 }} muted playsInline />

      {mensaje && <p style={{ fontSize: 13, color: "var(--cw-verde)" }}>{mensaje}</p>}

      <div className="tarjeta">
        {items.length === 0 && <p style={{ color: "var(--texto-secundario)", fontSize: 13 }}>Sin productos agregados todavía.</p>}
        {items.map((i) => (
          <div key={i.producto_id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", fontSize: 14 }}>
            <span>{i.cantidad} × {i.nombre}</span>
            <span>${(i.precio * i.cantidad).toFixed(2)}</span>
          </div>
        ))}
        {items.length > 0 && (
          <>
            <hr style={{ borderColor: "var(--borde)" }} />
            <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700 }}>
              <span>Total</span>
              <span>${total.toFixed(2)} MXN</span>
            </div>
            <button onClick={cobrar} className="boton-primario" style={{ width: "100%", marginTop: 12 }}>
              Generar cobro con Mercado Pago
            </button>
          </>
        )}
      </div>
    </div>
  );
}
