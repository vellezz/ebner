/*
 * Service worker: offline reading, and the receiving half of notifications.
 *
 * Caching is network-first for pages. A diary gains an entry every day, so a
 * cache-first shell would show yesterday's page to someone who opened the app
 * precisely to read today's. Offline, the cache answers.
 */

const VERSION = 'ebner-v1';
const SHELL = ['/', '/dni', '/sprawy', '/manifest.webmanifest', '/icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(VERSION)
      // Individually, so one missing URL cannot fail the whole install.
      .then((cache) => Promise.allSettled(SHELL.map((url) => cache.add(url))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // The subscription endpoint must never be served from cache.
  if (url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(VERSION).then((cache) => cache.put(request, copy));
        } else if (response.status === 404) {
          // An entry can be unpublished, and then this URL is gone for good.
          // Without this the cached copy survives forever and the app still
          // shows it offline — a removal that is complete everywhere except
          // on the devices that had read it.
          caches.open(VERSION).then((cache) => cache.delete(request));
        }
        return response;
      })
      .catch(async () => {
        const cached = await caches.match(request);
        if (cached) return cached;
        if (request.mode === 'navigate') return caches.match('/');
        throw new Error('offline and not cached');
      }),
  );
});

/*
 * Push carries no payload on purpose.
 *
 * A payload would have to be encrypted per subscription under RFC 8291, which
 * is a meaningful amount of cryptography to own for the sake of a title we can
 * simply fetch. The push is a nudge; the worker then asks the site what the
 * newest entry is.
 */
self.addEventListener('push', (event) => {
  event.waitUntil(
    (async () => {
      let title = 'Nowy wpis';
      let body = 'Ebner coś zapisał.';
      let url = '/';

      try {
        const response = await fetch('/api/latest.json', { cache: 'no-store' });
        if (response.ok) {
          const latest = await response.json();
          if (latest?.title) {
            title = latest.title;
            // Whatever text is shown arrives finished. Composing it here once
            // put "Dzień 7 · new_job" on a phone: `kind` is a stored English
            // identifier, and this end of the wire cannot translate it.
            body = latest.lead || latest.kind_label || `Dzień ${latest.day}`;
            url = `/dzien/${latest.day}`;
          }
        }
      } catch {
        // Offline or the endpoint is down: still notify, just generically.
      }

      await self.registration.showNotification(title, {
        body,
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-monochrome-96.png',
        lang: 'pl',
        tag: 'ebner-entry',
        data: { url },
      });
    })(),
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = event.notification.data?.url || '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      // Reuse an open window rather than piling up tabs.
      for (const client of clients) {
        if ('focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
