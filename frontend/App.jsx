import { BrowserRouter, Routes, Route } from "react-router-dom";
import { TemaProvider } from "./context/TemaContext";
import { AuthProvider } from "./context/AuthContext";
import Encabezado from "./components/Encabezado";
import ChatFlotante from "./components/ChatFlotante";
import RutaProtegida from "./components/RutaProtegida";
import Inicio from "./pages/Inicio";
import Login from "./pages/Login";
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
