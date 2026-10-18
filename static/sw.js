/* Service worker mínimo: guarda los estáticos para que la app abra sin conexión.
 * RED PRIMERO (desde 2026-10-18): siempre se pide la versión nueva y la copia
 * guardada solo se usa sin internet. Antes era "caché primero" y después de
 * cada despliegue el navegador seguía mostrando la versión vieja. Nunca cachea /api/* — el inventario debe
 * verse siempre fresco, nunca una copia vieja servida "offline" por error.
 * Sube CACHE_VERSION cuando cambien app.js/styles.css para forzar a los
 * navegadores con la app ya instalada a bajar la versión nueva. */
const CACHE_VERSION = 'chicoswheels-v35';
const ESTATICOS = ['/', '/app.js', '/styles.css', '/manifest.json', '/logo.webp'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE_VERSION).then((c) => c.addAll(ESTATICOS)));
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((claves) => Promise.all(
      claves.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Solo archivos de la propia app. Las fotos de Mattel/Shopify y las fuentes de
  // Google van directo: este worker hereda el CSP de la app (connect-src 'self')
  // y su fetch() a otro dominio falla, dejando la imagen rota (ERR_FAILED).
  if (url.origin !== self.location.origin) return;
  // La tienda (/tienda) y el bot (/bot) tampoco: deben verse siempre al día.
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/tienda') ||
      url.pathname.startsWith('/bot') || e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then((resp) => {
      if (resp.ok) {
        const copia = resp.clone();
        caches.open(CACHE_VERSION).then((c) => c.put(e.request, copia));
      }
      return resp;
    }).catch(() => caches.match(e.request))
  );
});
