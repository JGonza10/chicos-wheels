import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [usuario, setUsuario] = useState(null);
  const [cargando, setCargando] = useState(true);

  const cargarSesion = async () => {
    try {
      const datos = await api.get("/api/auth/sesion");
      setUsuario(datos.autenticado ? datos : null);
    } catch {
      setUsuario(null);
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargarSesion();
  }, []);

  const iniciarSesion = async (email, password) => {
    const datos = await api.post("/api/auth/login", { email, password });
    setUsuario({ ...datos, autenticado: true });
    return datos;
  };

  const registrar = async (nombre, email, password) => {
    const datos = await api.post("/api/auth/registro", { nombre, email, password });
    setUsuario({ ...datos, autenticado: true });
    return datos;
  };

  const cerrarSesion = async () => {
    await api.post("/api/auth/logout", {});
    setUsuario(null);
  };

  return (
    <AuthContext.Provider value={{ usuario, cargando, iniciarSesion, registrar, cerrarSesion }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
