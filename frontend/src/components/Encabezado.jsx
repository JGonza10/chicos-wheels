import { Link } from "react-router-dom";
import { useTema } from "../context/TemaContext";
import { useAuth } from "../context/AuthContext";

export default function Encabezado() {
  const { tema, alternarTema } = useTema();
  const { usuario, cerrarSesion } = useAuth();

  return (
    <header style={{ background: "var(--cw-azul)" }}>
      <div className="contenedor" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 20px" }}>
        <Link to="/" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ width: 30, height: 30, borderRadius: 6, background: "var(--cw-oro-claro)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, color: "var(--cw-azul)" }}>
            CW
          </span>
          <span style={{ color: "#fff", fontWeight: 700, fontSize: 18 }}>Chicos Wheels</span>
        </Link>

        <nav style={{ display: "flex", gap: 18, fontSize: 14, color: "#dfe9fb" }}>
          <Link to="/categoria/hot-wheels">Hot Wheels</Link>
          <Link to="/categoria/pokemon-tcg">Pokémon TCG</Link>
          <Link to="/ofertas">Ofertas</Link>
          {usuario?.rol && ["administrador", "vendedor"].includes(usuario.rol) && (
            <>
              <Link to="/panel/cobro">Cobrar</Link>
              <Link to="/panel/dashboard">Dashboard</Link>
            </>
          )}
        </nav>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button
            onClick={alternarTema}
            aria-label="Cambiar tema"
            style={{ background: "transparent", border: "none", color: "#dfe9fb", fontSize: 18 }}
          >
            {tema === "claro" ? "🌙" : "☀️"}
          </button>
          <Link to="/carrito" style={{ color: "#dfe9fb", fontSize: 18 }} aria-label="Carrito">🛒</Link>
          {usuario ? (
            <button onClick={cerrarSesion} className="boton-secundario" style={{ color: "#fff", borderColor: "#3a5a92" }}>
              Salir
            </button>
          ) : (
            <Link to="/login" className="boton-secundario" style={{ color: "#fff", borderColor: "#3a5a92" }}>
              Entrar
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
