// Generates the app icon as SVG, in three layouts.
//
// The mark is a lowercase "e" with a rust full stop — the head of the wordmark
// the masthead carries, `ebner.gripe`, set in the same face the site sets it
// in. The ground is the site's paper rather than its ink: a dark panel reads
// as equipment, and this is a diary.
//
// Two earlier attempts are worth naming so they are not repeated. A gauge with
// the needle in the red was apt for the world and read, unmistakably, as a rev
// counter. Letters cut from stacked rectangles read as an engineering drawing,
// because that is what they were — the fix was to set type rather than draw it.
//
// SVG is the source; `rasterise-icons.mjs` turns it into the committed PNGs in
// a browser, which is where the web font is available. The SVG is never served
// on its own for that reason: anywhere without Archivo would fall back to
// whatever sans it has and draw a different mark.
//
// Three layouts, because the purposes want different things:
//   any         — fills the square; the platform draws it as given.
//   maskable    — the same mark at 78%, so a circular or squircle mask has
//                 nothing of the letter to crop.
//   monochrome  — a white silhouette on transparency, which is the only thing
//                 Android will accept as a notification badge. Anything with
//                 colour or a ground comes out a solid white blob.

import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');

const GROUND = '#d3d0c8'; // --bg, the paper
const INK = '#1e1d1a'; // --fg
const ACCENT = '#8f4520'; // --ac, the full stop

const SIZE = 512;
// Archivo's lowercase sits low in the em box and `dominant-baseline` centres
// the em, not the letter, so the baseline is lifted until the "e" itself is
// centred. The x nudge offsets the full stop, which otherwise drags the pair
// left of centre.
const FONT_SIZE = 480;
const BASELINE = 220;
const CENTRE = 268;
// 0.78 keeps the letter inside the safe zone every mask respects.
const SAFE = 0.78;
const INSET = (SIZE * (1 - SAFE)) / 2;

const letter = (ink, dot) =>
  `  <text x="${CENTRE}" y="${BASELINE}" text-anchor="middle" dominant-baseline="central"` +
  ` font-family="Archivo, system-ui, sans-serif" font-weight="700" font-size="${FONT_SIZE}"` +
  ` fill="${ink}">e<tspan fill="${dot}">.</tspan></text>`;

function svg({ maskable = false, monochrome = false } = {}) {
  const body = monochrome ? letter('#ffffff', '#ffffff') : letter(INK, ACCENT);
  const placed =
    maskable || monochrome
      ? `  <g transform="translate(${INSET} ${INSET}) scale(${SAFE})">\n  ${body}\n  </g>`
      : body;
  const ground = monochrome ? '' : `  <rect width="${SIZE}" height="${SIZE}" fill="${GROUND}" />\n`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SIZE} ${SIZE}" width="${SIZE}" height="${SIZE}">
${ground}${placed}
</svg>
`;
}

mkdirSync(OUT, { recursive: true });
for (const [name, options] of [
  ['icon.svg', {}],
  ['icon-maskable.svg', { maskable: true }],
  ['icon-monochrome.svg', { monochrome: true }],
]) {
  const file = join(OUT, name);
  writeFileSync(file, svg(options), 'utf8');
  console.log(`  icons/${name}`);
}
