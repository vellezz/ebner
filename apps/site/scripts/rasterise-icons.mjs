// Turns the icon SVGs into the PNGs that actually ship.
//
// A browser does the rasterising because the mark is set type, and the web
// font only exists in a browser. This is why the SVGs are not served directly:
// anywhere without Archivo would substitute its own sans and draw a different
// letter.
//
// Run it when the mark changes, which is close to never:
//
//     pnpm --dir apps/site exec playwright install chromium   # once
//     node apps/site/scripts/rasterise-icons.mjs
//
// Playwright is not a dependency of this project. If it is not installed the
// script says so and stops, rather than leaving the committed PNGs half
// rewritten.

import { readFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ICONS = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');

// name → [source svg, size, transparent]
const TARGETS = [
  ['icon-512.png', 'icon.svg', 512, false],
  ['icon-192.png', 'icon.svg', 192, false],
  // iOS applies its own rounding and never a circular mask, so it takes the
  // full-bleed layout.
  ['icon-180.png', 'icon.svg', 180, false],
  ['icon-maskable-512.png', 'icon-maskable.svg', 512, false],
  ['icon-maskable-192.png', 'icon-maskable.svg', 192, false],
  ['icon-monochrome-96.png', 'icon-monochrome.svg', 96, true],
];

let chromium;
try {
  ({ chromium } = await import('playwright'));
} catch {
  console.error('  playwright is not installed — see the comment at the top of this file');
  process.exit(1);
}

const browser = await chromium.launch();
const page = await browser.newPage();

for (const [out, source, size, transparent] of TARGETS) {
  const svg = readFileSync(join(ICONS, source), 'utf8');
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<!doctype html><html><head><meta charset="utf-8">
     <link rel="preconnect" href="https://fonts.googleapis.com">
     <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
     <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@700&display=block" rel="stylesheet">
     <style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>
     </head><body>${svg}</body></html>`,
    { waitUntil: 'networkidle' },
  );
  // Without this the first icon can rasterise in the fallback face.
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(ICONS, out), omitBackground: transparent });
  console.log(`  icons/${out}  ${size}x${size}`);
}

await browser.close();
