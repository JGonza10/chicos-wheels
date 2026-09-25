/* Service worker mínimo: cachea los estáticos para que la app abra rápido
 * (y algo funcione sin conexión). Nunca cachea /api/* — el inventario debe
 * verse siempre fresco, nunca una copia vieja servida "offline" por error.
 * Sube CACHE_VERSION cuando cambien app.js/styles.css para forzar a los
 * navegadores con la app ya instalada a bajar la versión nueva. */
const CACHE_VERSION = 'chicoswheels-v17';
const ESTATICOS = ['/', '/app.js', '/styles.css', '/manifest.json'];

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
  if (url.pathname.startsWith('/api/') || e.request.method !== 'GET') return;
  e.respondWith(
    caches.match(e.request).then((cacheado) => cacheado || fetch(e.request).then((resp) => {
      const copia = resp.clone();
      caches.open(CACHE_VERSION).then((c) => c.put(e.request, copia));
      return resp;
    }).catch(() => cacheado))
  );
});
