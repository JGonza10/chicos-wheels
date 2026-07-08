import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { BASE_URL } from "../api";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const { iniciarSesion } = useAuth();
  const navegar = useNavigate();

  const enviar = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await iniciarSesion(email, password);
      navegar("/");
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="contenedor" style={{ maxWidth: 380, padding: "40px 20px" }}>
      <h1 style={{ fontSize: 20, marginBottom: 16 }}>Entrar a Chicos Wheels</h1>

      <form onSubmit={enviar} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <input type="email" placeholder="Correo" value={email} onChange={(e) => setEmail(e.target.value)}
          style={{ padding: 10, borderRadius: "var(--radio)", border: "1px solid var(--borde)", background: "var(--superficie)", color: "var(--texto)" }} />
        <input type="password" placeholder="Contraseña" value={password} onChange={(e) => setPassword(e.target.value)}
          style={{ padding: 10, borderRadius: "var(--radio)", border: "1px solid var(--borde)", background: "var(--superficie)", color: "var(--texto)" }} />
        {error && <p style={{ color: "var(--cw-naranja)", fontSize: 13 }}>{error}</p>}
        <button type="submit" className="boton-primario">Entrar</button>
      </form>

      <div style={{ margin: "18px 0", textAlign: "center", color: "var(--texto-secundario)", fontSize: 12 }}>o continúa con</div>

      <div style={{ display: "flex", gap: 8 }}>
        <a href={`${BASE_URL}/api/auth/social/google`} className="boton-secundario" style={{ flex: 1, textAlign: "center" }}>Google</a>
        <a href={`${BASE_URL}/api/auth/social/facebook`} className="boton-secundario" style={{ flex: 1, textAlign: "center" }}>Facebook</a>
      </div>
    </div>
  );
}
