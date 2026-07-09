const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:5000";

async function solicitud(ruta, opciones = {}) {
  const respuesta = await fetch(`${BASE_URL}${ruta}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...opciones,
  });

  const datos = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok) {
    throw new Error(datos.error || "Ocurrió un error al conectar con el servidor");
  }
  return datos;
}

export const api = {
  get: (ruta) => solicitud(ruta),
  post: (ruta, body) => solicitud(ruta, { method: "POST", body: JSON.stringify(body) }),
  put: (ruta, body) => solicitud(ruta, { method: "PUT", body: JSON.stringify(body) }),
  del: (ruta) => solicitud(ruta, { method: "DELETE" }),
};

export { BASE_URL };
