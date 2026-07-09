import { createContext, useContext, useEffect, useState } from "react";

const TemaContext = createContext(null);

export function TemaProvider({ children }) {
  const [tema, setTema] = useState(() => localStorage.getItem("cw-tema") || "claro");

  useEffect(() => {
    document.documentElement.setAttribute("data-tema", tema);
    localStorage.setItem("cw-tema", tema);
  }, [tema]);

  const alternarTema = () => setTema((actual) => (actual === "claro" ? "oscuro" : "claro"));

  return (
    <TemaContext.Provider value={{ tema, alternarTema }}>
      {children}
    </TemaContext.Provider>
  );
}

export function useTema() {
  return useContext(TemaContext);
}
