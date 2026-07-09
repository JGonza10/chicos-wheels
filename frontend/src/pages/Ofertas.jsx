import { useEffect, useState } from "react";
import { api } from "../api";

export default function Ofertas() {
  const [ofertas, setOfertas] = useState([]);

  useEffect(() => {
    api.get("/api/ofertas").then(setOfertas).catch(() => setOfertas([]));
  }, []);

  return (
    <div className="contenedor" style={{ padding: "24px 20px" }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Ofertas activas</h1>

      {ofertas.length === 0 && <p style={{ color: "var(--texto-secundario)" }}>No hay ofertas activas por ahora.</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {ofertas.map((o) => (
          <div key={o.id} className="tarjeta">
            <p style={{ margin: 0, fontWeight: 700 }}>{o.titulo}</p>
            <p style={{ margin: "4px 0", fontSize: 13, color: "var(--texto-secundario)" }}>{o.descripcion}</p>
            <p style={{ margin: 0, fontSize: 12, color: "var(--cw-naranja)" }}>
              Termina el {new Date(o.fecha_fin).toLocaleDateString("es-MX")}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
