// Generates a VAPID key pair for Web Push.
//
// The public key is printed: it ships in the page, because the browser needs
// it to create a subscription. The private key is written to a gitignored file
// and never printed — it is the credential that proves pushes come from this
// site, and the only place it belongs afterwards is a repository secret.
//
//   node scripts/vapid-keys.mjs
//   gh secret set VAPID_PRIVATE_KEY --repo vellezz/ebner < .vapid-private.key
//   rm .vapid-private.key

import { generateKeyPairSync } from 'node:crypto';
import { writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

const { publicKey, privateKey } = generateKeyPairSync('ec', { namedCurve: 'prime256v1' });
const pub = publicKey.export({ format: 'jwk' });
const priv = privateKey.export({ format: 'jwk' });

const b64url = (buf) => Buffer.from(buf).toString('base64url');
const fromB64url = (s) => Buffer.from(s, 'base64url');

// VAPID wants the uncompressed EC point: 0x04 || X || Y.
const uncompressed = Buffer.concat([
  Buffer.from([0x04]),
  fromB64url(pub.x),
  fromB64url(pub.y),
]);

const keyFile = join(ROOT, '.vapid-private.key');
writeFileSync(keyFile, priv.d, { encoding: 'utf8' });

console.log('  klucz publiczny (do strony):');
console.log('  ' + b64url(uncompressed));
console.log('');
console.log('  klucz prywatny zapisany do: .vapid-private.key  (ignorowany przez git)');
console.log('  gh secret set VAPID_PRIVATE_KEY --repo vellezz/ebner < .vapid-private.key');
console.log('  potem skasuj plik');
