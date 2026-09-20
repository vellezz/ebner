/**
 * The site Worker.
 *
 * It was assets-only until notifications needed somewhere to put a
 * subscription. It still serves nothing dynamic that a reader can see: every
 * page, and even the newest-entry JSON the service worker reads, is a static
 * file built from content/. The only dynamic surface is subscribing.
 *
 * This is the one place where the site touches D1, and it touches exactly one
 * table — push_subscriptions, which is also the only table that is not a
 * projection of content/state/. No world state is read or written here.
 */

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });

/** Endpoints come from the browser's push service; accept only real ones. */
function validEndpoint(value) {
  if (typeof value !== 'string' || value.length > 1024) return false;
  try {
    return new URL(value).protocol === 'https:';
  } catch {
    return false;
  }
}

async function subscribe(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'malformed body' }, 400);
  }

  const { endpoint, keys } = body ?? {};
  if (!validEndpoint(endpoint) || !keys?.p256dh || !keys?.auth) {
    return json({ error: 'incomplete subscription' }, 400);
  }

  // The endpoint is the identity: a browser reissues it on rotation and the
  // old one stops working, so replacing on it keeps the table honest. Writing
  // gone_at back to NULL matters — a previously dead endpoint can come back.
  await env.DB.prepare(
    'INSERT INTO push_subscriptions (endpoint, p256dh, auth, created_at, gone_at) ' +
      "VALUES (?, ?, ?, datetime('now'), NULL) " +
      'ON CONFLICT(endpoint) DO UPDATE SET ' +
      'p256dh = excluded.p256dh, auth = excluded.auth, gone_at = NULL',
  )
    .bind(endpoint, String(keys.p256dh), String(keys.auth))
    .run();

  return json({ ok: true });
}

async function unsubscribe(request, env) {
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: 'malformed body' }, 400);
  }
  if (!validEndpoint(body?.endpoint)) return json({ error: 'no endpoint' }, 400);

  await env.DB.prepare('DELETE FROM push_subscriptions WHERE endpoint = ?')
    .bind(body.endpoint)
    .run();
  return json({ ok: true });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === '/api/subscribe' && request.method === 'POST') {
      return subscribe(request, env);
    }
    if (url.pathname === '/api/unsubscribe' && request.method === 'POST') {
      return unsubscribe(request, env);
    }
    if (url.pathname.startsWith('/api/') && !url.pathname.endsWith('.json')) {
      return json({ error: 'not found' }, 404);
    }

    // Everything else is a file built from content/.
    return env.ASSETS.fetch(request);
  },
};
