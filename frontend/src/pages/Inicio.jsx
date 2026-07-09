import { useEffect, useState } from "react";
import { api } from "../api";
import TarjetaProducto from "../components/TarjetaProducto";

export default function Inicio() {
  const [destacados, setDestacados] = useState([]);

  useEffect(() => {
    api.get("/api/productos?destacados=true").then(setDestacados).catch(() => setDestacados([]));
  }, []);

  return (
    <div>
      <section style={{ background: "var(--cw-naranja)", padding: "26px 20px" }}>
        <div className="contenedor" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 16 }}>
          <div>
            <span style={{ background: "var(--cw-oro-claro)", color: "#4a3300", fontSize: 12, fontWeight: 700, padding: "3px 10px", borderRadius: 20 }}>
              Envío gratis desde $599
            </span>
            <h1 style={{ color: "#fff", fontSize: 28, margin: "10px 0 4px" }}>Ofertas de temporada · hasta 30% off</h1>
            <p style={{ color: "#ffe4d2", margin: 0, fontSize: 14 }}>Piezas de edición limitada, stock reducido.</p>
          </div>
          <a href="/ofertas" className="boton-secundario" style={{ background: "var(--cw-azul)", color: "#fff", borderColor: "var(--cw-azul)" }}>
            Ver ofertas →
          </a>
        </div>
      </section>

      <section className="contenedor" style={{ padding: "24px 20px" }}>
        <h2 style={{ fontSize: 18, marginBottom: 14 }}>Destacados con descuento</h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 16 }}>
          {destacados.map((p) => <TarjetaProducto key={p.id} producto={p} />)}
          {destacados.length === 0 && (
            <p style={{ color: "var(--texto-secundario)" }}>Aún no hay productos destacados cargados.</p>
          )}
        </div>
      </section>
    </div>
  );
}
