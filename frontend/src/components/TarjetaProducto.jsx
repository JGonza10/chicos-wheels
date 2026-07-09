import { api } from "../api";

export default function TarjetaProducto({ producto }) {
  const agregarAlCarrito = async () => {
    try {
      await api.post("/api/carrito/agregar", { producto_id: producto.id, cantidad: 1 });
      alert(`${producto.nombre} se agregó al carrito`);
    } catch (error) {
      alert(error.message);
    }
  };

  const compartir = (red) => {
    const url = `${window.location.origin}/producto/${producto.id}`;
    const texto = encodeURIComponent(`Mira esto en Chicos Wheels: ${producto.nombre}`);
    const enlaces = {
      whatsapp: `https://wa.me/?text=${texto}%20${url}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${url}`,
    };
    window.open(enlaces[red], "_blank", "noopener");
  };

  return (
    <div className="tarjeta" style={{ position: "relative" }}>
      {producto.descuento > 0 && (
        <span className="etiqueta-descuento" style={{ position: "absolute", top: 10, right: 10 }}>
          -{producto.descuento}%
        </span>
      )}
      {producto.stock > 0 && producto.stock <= 5 && (
        <span className="etiqueta-escasez" style={{ position: "absolute", top: 10, left: 10 }}>
          Solo {producto.stock}
        </span>
      )}

      <div style={{ height: 130, background: "var(--fondo)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
        {producto.imagen_url ? (
          <img src={producto.imagen_url} alt={producto.nombre} style={{ maxHeight: "100%", maxWidth: "100%" }} />
        ) : (
          <span style={{ color: "var(--texto-secundario)", fontSize: 12 }}>Sin imagen</span>
        )}
      </div>

      <p style={{ fontSize: 14, margin: "0 0 4px", fontWeight: 600 }}>{producto.nombre}</p>
      <p style={{ fontSize: 12, color: "var(--texto-secundario)", margin: "0 0 8px" }}>{producto.categoria}</p>

      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 10 }}>
        {producto.precio_anterior && <span className="precio-anterior">${producto.precio_anterior}</span>}
        <span className="precio-actual">${producto.precio} MXN</span>
      </div>

      <button className="boton-primario" style={{ width: "100%", marginBottom: 8 }} onClick={agregarAlCarrito}>
        Agregar al carrito
      </button>

      <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
        <button onClick={() => compartir("whatsapp")} className="boton-secundario" style={{ flex: 1, fontSize: 12 }}>
          WhatsApp
        </button>
        <button onClick={() => compartir("facebook")} className="boton-secundario" style={{ flex: 1, fontSize: 12 }}>
          Facebook
        </button>
      </div>
    </div>
  );
}
