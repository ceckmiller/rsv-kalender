const CACHE_NAME = 'rsv-2-1-final-v23';
const APP_SHELL = [
  '/',
  '/index.html',
  '/site.webmanifest',
  '/assets/rsv-logo.png',
  '/favicon.ico',
  '/favicon-32x32.png',
  '/apple-touch-icon.png',
  '/android-chrome-192x192.png',
  '/android-chrome-512x512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.endsWith('.ics') || url.pathname.endsWith('site-data.json') || url.pathname.startsWith('/api/') || url.pathname.startsWith('/.netlify/functions/')) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request).then(r => r || caches.match('/index.html'))));
});
