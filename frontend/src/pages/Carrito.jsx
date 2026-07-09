import { useEffect, useState } from "react";
import { api } from "../api";

export default function Carrito() {
  const [carrito, setCarrito] = useState({ items: [], total: 0 });
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");

  const cargar = async () => {
    setCargando(true);
    try {
      setCarrito(await api.get("/api/carrito"));
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => { cargar(); }, []);

  const cambiarCantidad = async (itemId, cantidad) => {
    await api.put(`/api/carrito/item/${itemId}`, { cantidad });
    cargar();
  };

  const eliminar = async (itemId) => {
    await api.del(`/api/carrito/item/${itemId}`);
    cargar();
  };

  const pagar = async () => {
    try {
      const respuesta = await api.post("/api/pedidos/checkout", {});
      window.location.href = respuesta.link_pago;
    } catch (err) {
      setError(err.message);
    }
  };

  if (cargando) return <div className="contenedor" style={{ padding: 24 }}>Cargando…</div>;

  if (error === "No autenticado") {
    return (
      <div className="contenedor" style={{ padding: 24 }}>
        <p>Inicia sesión para ver tu carrito.</p>
        <a href="/login" className="boton-primario">Entrar</a>
      </div>
    );
  }

  return (
    <div className="contenedor" style={{ padding: "24px 20px", maxWidth: 560 }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Tu carrito</h1>

      {carrito.items.length === 0 && <p style={{ color: "var(--texto-secundario)" }}>Tu carrito está vacío.</p>}

      {carrito.items.map((item) => (
        <div key={item.item_id} className="tarjeta" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>{item.nombre}</p>
            <p style={{ margin: "2px 0 0", fontSize: 12, color: "var(--texto-secundario)" }}>${item.precio} MXN c/u</p>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <button className="boton-secundario" onClick={() => cambiarCantidad(item.item_id, item.cantidad - 1)}>-</button>
            <span>{item.cantidad}</span>
            <button className="boton-secundario" onClick={() => cambiarCantidad(item.item_id, item.cantidad + 1)}>+</button>
            <button className="boton-secundario" onClick={() => eliminar(item.item_id)}>Quitar</button>
          </div>
        </div>
      ))}

      {carrito.items.length > 0 && (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", fontWeight: 700, fontSize: 16, margin: "16px 0" }}>
            <span>Total</span>
            <span>${carrito.total} MXN</span>
          </div>
          <button className="boton-primario" style={{ width: "100%" }} onClick={pagar}>
            Pagar con Mercado Pago
          </button>
        </>
      )}

      {error && error !== "No autenticado" && <p style={{ color: "var(--cw-naranja)" }}>{error}</p>}
    </div>
  );
}
