// Installable shell only. Never cache athlete, medical, session or report responses.
const CACHE = 'ascentiq-shell-v3';
const PUBLIC = ['/offline.html','/icon.svg','/icon-180.png','/icon-192.png','/icon-512.png','/icon-maskable.png'];
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(PUBLIC))); self.skipWaiting(); });
self.addEventListener('activate', event => event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('ascentiq-shell-') && key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(()=>caches.match('/offline.html')));
  } else if (PUBLIC.includes(url.pathname)) {
    event.respondWith(caches.match(event.request).then(cached=>cached || fetch(event.request)));
  }
});
