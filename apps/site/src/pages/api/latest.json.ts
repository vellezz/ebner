import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';

/**
 * The newest entry, as static JSON.
 *
 * Built from content/ like everything else, which keeps the notification path
 * off D1 entirely: the service worker wakes on a payload-less push and asks
 * here what to say. A dynamic endpoint would have meant the site reading world
 * state at request time, and the site does not do that.
 */
export const GET: APIRoute = async () => {
  const entries = await getCollection('entries');
  const latest = entries.sort((a, b) => b.data.day - a.data.day)[0];

  const body = latest
    ? {
        day: latest.data.day,
        title: latest.data.title,
        kind: latest.data.kind,
        location: latest.data.location,
        url: `/dzien/${latest.data.day}`,
      }
    : null;

  return new Response(JSON.stringify(body), {
    headers: {
      'content-type': 'application/json; charset=utf-8',
      // Short, because a notification arriving before this updates would
      // announce yesterday.
      'cache-control': 'public, max-age=60',
    },
  });
};
