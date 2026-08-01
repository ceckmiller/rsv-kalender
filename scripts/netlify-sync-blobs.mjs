import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { getStore } from '@netlify/blobs';

const files = ['site-data.json', 'rsv-regionalliga.ics', 'rsv-u23.ics', 'rsv-u21.ics', 'rsv-u19.ics', 'venue-cache.json'];

function contentHash(file, content) {
  if (file === 'site-data.json') {
    const data = JSON.parse(content);
    delete data.generated_at;
    return createHash('sha256').update(JSON.stringify(data)).digest('hex');
  }
  return createHash('sha256').update(content).digest('hex');
}

const siteID = process.env.NETLIFY_SITE_ID || process.env.SITE_ID || 'd6f89f9b-e623-4ede-81e7-806e81426603';
const token = process.env.NETLIFY_AUTH_TOKEN || process.env.NETLIFY_API_TOKEN || '';

if (!token) {
  console.log('Blob-Sync übersprungen: NETLIFY_AUTH_TOKEN fehlt im Build (optional, GitHub Actions publiziert direkt).');
  process.exit(0);
}

const store = getStore('rsv-live-data', { siteID, token });
let changed = 0;

for (const file of files) {
  const path = file === 'venue-cache.json' ? `data/${file}` : `docs/${file}`;
  let content;
  try {
    content = await readFile(path, 'utf8');
  } catch {
    console.log(`= ${file}: nicht vorhanden, übersprungen`);
    continue;
  }
  const newHash = contentHash(file, content);
  const oldHash = await store.get(`${file}.sha256`, { type: 'text' });
  if (oldHash === newHash) {
    console.log(`= ${file}: unverändert`);
    continue;
  }
  await store.set(file, content, { metadata: { sha256: newHash, updatedAt: new Date().toISOString() } });
  await store.set(`${file}.sha256`, newHash);
  changed += 1;
  console.log(`✓ ${file}: in Blobs übernommen`);
}

console.log(changed ? `Netlify-Build: ${changed} Datei(en) in Blobs aktualisiert.` : 'Netlify-Build: Blobs bereits aktuell.');
