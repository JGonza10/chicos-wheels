import { useState } from "react";
import { api } from "../api";

export default function ChatFlotante() {
  const [abierto, setAbierto] = useState(false);
  const [mensajes, setMensajes] = useState([
    { de: "bot", texto: "¡Hola! Soy el asistente de Chicos Wheels. ¿En qué te ayudo?" },
  ]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);

  const enviar = async () => {
    if (!texto.trim()) return;
    const propio = texto;
    setMensajes((prev) => [...prev, { de: "yo", texto: propio }]);
    setTexto("");
    setEnviando(true);

    try {
      const respuesta = await api.post("/api/chatbot/mensaje", { mensaje: propio });
      setMensajes((prev) => [...prev, { de: "bot", texto: respuesta.respuesta }]);
    } catch {
      setMensajes((prev) => [...prev, { de: "bot", texto: "No pude responder en este momento, intenta de nuevo." }]);
    } finally {
      setEnviando(false);
    }
  };

  if (!abierto) {
    return (
      <button
        onClick={() => setAbierto(true)}
        aria-label="Abrir chat"
        style={{
          position: "fixed", bottom: 20, right: 20, width: 52, height: 52, borderRadius: "50%",
          background: "var(--cw-naranja)", color: "#fff", border: "none", fontSize: 20, boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
        }}
      >
        💬
      </button>
    );
  }

  return (
    <div style={{
      position: "fixed", bottom: 20, right: 20, width: 300, maxHeight: 420, display: "flex", flexDirection: "column",
      background: "var(--superficie)", border: "1px solid var(--borde)", borderRadius: 12, overflow: "hidden",
      boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
    }}>
      <div style={{ background: "var(--cw-azul)", color: "#fff", padding: "10px 14px", display: "flex", justifyContent: "space-between" }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>Asistente Chicos Wheels</span>
        <button onClick={() => setAbierto(false)} style={{ background: "transparent", border: "none", color: "#fff" }}>✕</button>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
        {mensajes.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.de === "yo" ? "flex-end" : "flex-start",
            background: m.de === "yo" ? "var(--cw-naranja)" : "var(--fondo)",
            color: m.de === "yo" ? "#fff" : "var(--texto)",
            padding: "6px 10px", borderRadius: 10, fontSize: 13, maxWidth: "85%",
          }}>
            {m.texto}
          </div>
        ))}
        {enviando && <div style={{ fontSize: 12, color: "var(--texto-secundario)" }}>Escribiendo…</div>}
      </div>

      <div style={{ display: "flex", borderTop: "1px solid var(--borde)" }}>
        <input
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviar()}
          placeholder="Escribe tu pregunta…"
          style={{ flex: 1, border: "none", padding: 10, fontSize: 13, background: "transparent", color: "var(--texto)" }}
        />
        <button onClick={enviar} style={{ background: "transparent", border: "none", padding: "0 12px", color: "var(--cw-naranja)", fontWeight: 600 }}>
          Enviar
        </button>
      </div>
    </div>
  );
}
