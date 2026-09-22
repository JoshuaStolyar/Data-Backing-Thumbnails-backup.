const CACHE_NAME = 'databacking-v1';

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(['/'])));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(names => Promise.all(names.filter(n => n !== CACHE_NAME).map(n => caches.delete(n))))
  );
  self.clients.claim();
});

// network-first so everyone gets the freshest data while online; falls back to
// whatever was last cached (page, scripts, API responses) when the network fails,
// so the team can keep using the tool through an outage instead of seeing a blank page.
// Thumbnails are skipped so the cache doesn't grow unbounded with every video image seen.
self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET' || req.destination === 'image') return;
  event.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then(cache => cache.put(req, copy));
      return res;
    }).catch(() => caches.match(req).then(cached => cached || (req.mode === 'navigate' ? caches.match('/') : undefined)))
  );
});
