import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api";
import TarjetaProducto from "../components/TarjetaProducto";

const TITULOS = {
  "hot-wheels": "Hot Wheels",
  "pokemon-tcg": "Pokémon TCG",
  "accesorios": "Accesorios y coleccionables",
};

export default function Categoria() {
  const { slug } = useParams();
  const [productos, setProductos] = useState([]);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    setCargando(true);
    api.get(`/api/productos?categoria=${slug}`)
      .then(setProductos)
      .finally(() => setCargando(false));
  }, [slug]);

  return (
    <div className="contenedor" style={{ padding: "24px 20px" }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>{TITULOS[slug] || slug}</h1>

      {cargando && <p style={{ color: "var(--texto-secundario)" }}>Cargando productos…</p>}
      {!cargando && productos.length === 0 && (
        <p style={{ color: "var(--texto-secundario)" }}>Todavía no hay productos en esta categoría.</p>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 16 }}>
        {productos.map((p) => <TarjetaProducto key={p.id} producto={p} />)}
      </div>
    </div>
  );
}
