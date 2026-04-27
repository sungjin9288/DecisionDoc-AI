const CACHE_NAME = 'decisiondoc-v1.1.17';
const OFFLINE_URL = '/offline.html';
const HTML_SHELL_PATHS = new Set(['/', '/static/index.html']);

// Static assets to cache on install
const PRECACHE_URLS = [
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  OFFLINE_URL,
];

// API routes to cache with network-first strategy
const API_CACHE_PATTERNS = [
  /\/bundles$/,
  /\/projects\?/,
  /\/styles$/,
  /\/dashboard\/overview$/,
];

// Install: precache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_URLS).catch(err => {
        console.warn('[SW] Precache partial failure:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME)
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Fetch strategy
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET, cross-origin, SSE streams
  if (request.method !== 'GET') return;
  if (url.origin !== location.origin) return;
  if (url.pathname.includes('/generate/stream')) return;
  if (url.pathname.includes('/generate/sketch')) return;

  // API calls: network-first, fall back to cache
  if (url.pathname.startsWith('/') &&
      (url.pathname.match(/\/(bundles|projects|styles|dashboard|notifications)/) ||
       API_CACHE_PATTERNS.some(p => p.test(url.pathname + url.search)))) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // HTML shell: always prefer the network so deployments are visible after reload.
  if (HTML_SHELL_PATHS.has(url.pathname) || request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(networkFirstHtmlStrategy(request));
    return;
  }

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }
});

async function networkFirstHtmlStrategy(request) {
  try {
    return await fetch(request, { cache: 'no-store' });
  } catch {
    return caches.match(OFFLINE_URL);
  }
}

async function networkFirstStrategy(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || new Response(
      JSON.stringify({ error: '오프라인 상태입니다.', offline: true }),
      { headers: { 'Content-Type': 'application/json' }, status: 503 }
    );
  }
}

async function cacheFirstStrategy(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response('Resource unavailable offline', { status: 503 });
  }
}

// Push notification handler
self.addEventListener('push', event => {
  if (!event.data) return;

  try {
    const data = event.data.json();
    event.waitUntil(
      self.registration.showNotification(data.title || 'DecisionDoc AI', {
        body: data.body || '',
        icon: '/static/icons/icon-192.png',
        badge: '/static/icons/icon-192.png',
        tag: data.tag || 'decisiondoc',
        data: { url: data.action_url || '/' },
        actions: data.action_url ? [
          { action: 'open', title: '바로가기' }
        ] : []
      })
    );
  } catch(e) {
    console.error('[SW] Push notification error:', e);
  }
});

// Notification click handler
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(clientList => {
        for (const client of clientList) {
          if (client.url === url && 'focus' in client) {
            return client.focus();
          }
        }
        return clients.openWindow(url);
      })
  );
});
