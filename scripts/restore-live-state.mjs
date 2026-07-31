import { mkdir, writeFile } from 'node:fs/promises';
import { getStore } from '@netlify/blobs';

const siteID = process.env.NETLIFY_SITE_ID;
const token = process.env.NETLIFY_AUTH_TOKEN;
if (!siteID || !token) {
  console.log('Kein Netlify-Zugang für Cache-Wiederherstellung; lokaler Ausgangsstand wird verwendet.');
  process.exit(0);
}
const store = getStore('rsv-live-data', { siteID, token });
const value = await store.get('venue-cache.json', { type: 'text' });
if (!value) {
  console.log('Noch keine Spielortdatenbank in Netlify Blobs vorhanden.');
  process.exit(0);
}
await mkdir(new URL('../data/', import.meta.url), { recursive: true });
await writeFile(new URL('../data/venue-cache.json', import.meta.url), value, 'utf8');
console.log('Bestehende Spielortdatenbank aus Netlify Blobs geladen.');
