// Generates the app icons.
//
// Written by hand rather than with an image library on purpose: sharp is in
// the dependency tree but pnpm refuses to run its build scripts here, and an
// icon this simple does not justify fighting that. A PNG is a handful of
// chunks around a zlib stream, so the encoder below is the whole of it.
//
// The mark is the gate at Hoonu: three rings, and the third one does not line
// up with the others because somebody bolted it to zero.

import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons');

const GROUND = [30, 29, 26]; // --fg
const BAR = [211, 208, 200]; // --bg
const ACCENT = [143, 69, 32]; // --ac

const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const byte of buf) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};

function chunk(type, data) {
  const out = Buffer.alloc(data.length + 12);
  out.writeUInt32BE(data.length, 0);
  out.write(type, 4, 'ascii');
  data.copy(out, 8);
  out.writeUInt32BE(crc32(Buffer.concat([Buffer.from(type, 'ascii'), data])), data.length + 8);
  return out;
}

function png(size, pixel) {
  // One filter byte (0 = none) per scanline, then RGB triples.
  const raw = Buffer.alloc(size * (size * 3 + 1));
  let at = 0;
  for (let y = 0; y < size; y++) {
    raw[at++] = 0;
    for (let x = 0; x < size; x++) {
      const [r, g, b] = pixel(x, y, size);
      raw[at++] = r;
      raw[at++] = g;
      raw[at++] = b;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 2; // colour type: truecolour
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

/** Three bars; the third sits off the axis the other two share. */
function mark(x, y, size) {
  const u = size / 16;
  const inset = 3 * u;
  const barHeight = 1.6 * u;
  const gap = 2.4 * u;
  const top = size / 2 - gap - barHeight / 2;

  for (let i = 0; i < 3; i++) {
    const y0 = top + i * gap;
    if (y < y0 || y >= y0 + barHeight) continue;
    // The third bar is short and shifted — the ring that will not turn.
    const left = i === 2 ? inset + 2.6 * u : inset;
    const right = i === 2 ? size - inset - 2.2 * u : size - inset;
    if (x >= left && x < right) return i === 2 ? ACCENT : BAR;
  }
  return GROUND;
}

mkdirSync(OUT, { recursive: true });
for (const size of [180, 192, 512]) {
  const file = join(OUT, `icon-${size}.png`);
  writeFileSync(file, png(size, mark));
  console.log(`  ${file.split(/[\\/]/).slice(-2).join('/')}  ${size}x${size}`);
}
