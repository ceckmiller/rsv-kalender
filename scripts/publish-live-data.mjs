import { createHash } from 'node:crypto';
import { appendFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { getStore } from '@netlify/blobs';

const siteID = process.env.NETLIFY_SITE_ID;
const token = process.env.NETLIFY_AUTH_TOKEN;
if (!siteID || !token) throw new Error('NETLIFY_SITE_ID und NETLIFY_AUTH_TOKEN müssen gesetzt sein.');

const store = getStore('rsv-live-data', { siteID, token });
const files = ['site-data.json', 'rsv-herren.ics', 'rsv-regionalliga.ics', 'rsv-u23.ics', 'rsv-u21.ics', 'rsv-u19.ics', 'hertha-bsc.ics', 'venue-cache.json'];
let changed = 0;

function contentHash(file, content) {
  if (file === 'site-data.json') {
    const data = JSON.parse(content);
    delete data.generated_at;
    return createHash('sha256').update(JSON.stringify(data)).digest('hex');
  }
  return createHash('sha256').update(content).digest('hex');
}

for (const file of files) {
  const content = await readFile(new URL(file === 'venue-cache.json' ? '../data/venue-cache.json' : `../docs/${file}`, import.meta.url), 'utf8');
  const newHash = contentHash(file, content);
  const oldHash = await store.get(`${file}.sha256`, { type: 'text' });
  if (oldHash === newHash) {
    console.log(`= ${file}: unverändert`);
    continue;
  }
  await store.set(file, content, { metadata: { sha256: newHash, updatedAt: new Date().toISOString() } });
  await store.set(`${file}.sha256`, newHash);
  changed += 1;
  console.log(`✓ ${file}: aktualisiert`);
}

console.log(changed ? `Daten veröffentlicht: ${changed} Datei(en) geändert.` : 'Keine Änderungen – Veröffentlichung übersprungen.');

const output = process.env.GITHUB_OUTPUT;
if (output) {
  appendFileSync(output, `changed=${changed > 0 ? 'true' : 'false'}\n`);
  appendFileSync(output, `changed_count=${changed}\n`);
}

process.exit(0);
