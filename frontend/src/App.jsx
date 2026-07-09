import { BrowserRouter, Routes, Route } from "react-router-dom";
import { TemaProvider } from "./context/TemaContext";
import { AuthProvider } from "./context/AuthContext";
import Encabezado from "./components/Encabezado";
import ChatFlotante from "./components/ChatFlotante";
import RutaProtegida from "./components/RutaProtegida";
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
import Carrito from "./pages/Carrito";
import Categoria from "./pages/Categoria";
import Ofertas from "./pages/Ofertas";
import Dashboard from "./pages/Dashboard";
import PanelCobro from "./pages/PanelCobro";

export default function App() {
  return (
    <TemaProvider>
      <AuthProvider>
        <BrowserRouter>
          <Encabezado />
          <Routes>
            <Route path="/" element={<Inicio />} />
            <Route path="/login" element={<Login />} />
            <Route path="/carrito" element={<Carrito />} />
            <Route path="/categoria/:slug" element={<Categoria />} />
            <Route path="/ofertas" element={<Ofertas />} />
            <Route
              path="/panel/dashboard"
              element={
                <RutaProtegida roles={["administrador", "vendedor"]}>
                  <Dashboard />
                </RutaProtegida>
              }
            />
            <Route
              path="/panel/cobro"
              element={
                <RutaProtegida roles={["administrador", "vendedor"]}>
                  <PanelCobro />
                </RutaProtegida>
              }
            />
          </Routes>
          <ChatFlotante />
        </BrowserRouter>
      </AuthProvider>
    </TemaProvider>
  );
}
