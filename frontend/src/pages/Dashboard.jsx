import { useEffect, useState } from "react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { api } from "../api";

export default function Dashboard() {
  const [datos, setDatos] = useState(null);

  useEffect(() => {
    api.get("/api/dashboard/resumen").then(setDatos).catch(() => setDatos(null));
  }, []);

  if (!datos) return <div className="contenedor" style={{ padding: 24 }}>Cargando…</div>;

  return (
    <div className="contenedor" style={{ padding: "24px 20px" }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Dashboard de ventas</h1>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 24 }}>
        <div className="tarjeta">
          <p style={{ fontSize: 12, color: "var(--texto-secundario)", margin: 0 }}>Ventas totales</p>
          <p style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>${datos.total_ventas.toFixed(2)}</p>
        </div>
        <div className="tarjeta">
          <p style={{ fontSize: 12, color: "var(--texto-secundario)", margin: 0 }}>Pedidos pagados</p>
          <p style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>{datos.total_pedidos}</p>
        </div>
        <div className="tarjeta">
          <p style={{ fontSize: 12, color: "var(--texto-secundario)", margin: 0 }}>Pendientes</p>
          <p style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>{datos.por_estado.pendiente || 0}</p>
        </div>
      </div>

      <h2 style={{ fontSize: 15, marginBottom: 8 }}>Ventas últimos 7 días</h2>
      <div style={{ height: 220, marginBottom: 28 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={datos.ventas_por_dia}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" />
            <XAxis dataKey="fecha" fontSize={11} />
            <YAxis fontSize={11} />
            <Tooltip />
            <Line type="monotone" dataKey="total" stroke="var(--cw-naranja, #e8622c)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <h2 style={{ fontSize: 15, marginBottom: 8 }}>Productos más vendidos</h2>
      <div style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={datos.mas_vendidos} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="var(--borde)" />
            <XAxis type="number" fontSize={11} />
            <YAxis dataKey="nombre" type="category" width={140} fontSize={11} />
            <Tooltip />
            <Bar dataKey="unidades" fill="#123c7a" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
