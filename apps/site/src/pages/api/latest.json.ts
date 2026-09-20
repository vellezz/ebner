import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { kindLabel } from '../../lib/kinds';

/**
 * The newest entry, as static JSON.
 *
 * Built from content/ like everything else, which keeps the notification path
 * off D1 entirely: the service worker wakes on a payload-less push and asks
 * here what to say. A dynamic endpoint would have meant the site reading world
 * state at request time, and the site does not do that.
 *
 * Everything a notification displays is finished Polish by the time it leaves
 * here. The service worker composed its own text once and shipped "Dzień 7 ·
 * new_job" to a phone — a stored enum value has no business being assembled
 * into a sentence at the far end.
 */

/** The opening of the entry, as a line of plain prose. */
function lead(markdown: string, limit = 130): string {
  const paragraph = markdown
    .split(/\n\s*\n/)
    // Skip an entry that opens on a quoted document or a heading: it is not a
    // sentence, and cropping it reads as damage.
    .find((block) => /^[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż„—]/.test(block.trim()));
  if (!paragraph) return '';

  const text = paragraph
    .replace(/\s+/g, ' ')
    .replace(/[*_`]/g, '')
    .replace(/\[([^\]]+)\]\([^)]*\)/g, '$1')
    .trim();
  if (text.length <= limit) return text;

  // Prefer to end on a sentence, then on a word, and never mid-syllable.
  const head = text.slice(0, limit);
  const sentence = head.lastIndexOf('. ');
  if (sentence > limit * 0.5) return head.slice(0, sentence + 1);
  return head.slice(0, head.lastIndexOf(' ')).replace(/[,;:—-]$/, '') + '…';
}

export const GET: APIRoute = async () => {
  const entries = await getCollection('entries');
  const latest = entries.sort((a, b) => b.data.day - a.data.day)[0];

  const body = latest
    ? {
        day: latest.data.day,
        title: latest.data.title,
        kind: latest.data.kind,
        kind_label: kindLabel(latest.data.kind),
        lead: lead(latest.body ?? ''),
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
