import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { getStore } from '@netlify/blobs';

const files = new Set([
  'rsv-herren.ics',
  'rsv-regionalliga.ics',
  'rsv-u23.ics',
  'rsv-u21.ics',
  'rsv-u19.ics',
  'hertha-bsc.ics',
]);

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

async function readBundled(file) {
  const paths = [
    join(process.cwd(), 'docs', file),
    join(process.cwd(), file),
  ];
  for (const path of paths) {
    try {
      return await readFile(path, 'utf8');
    } catch {
      // try next candidate
    }
  }
  return null;
}

async function pickCalendarText(store, file) {
  const bundled = await readBundled(file);
  let blob = null;
  let blobHash = null;
  try {
    blob = await store.get(file, { type: 'text' });
    blobHash = await store.get(`${file}.sha256`, { type: 'text' });
  } catch {
    // blob store unavailable
  }
  if (bundled && blob) {
    const bundledHash = sha256(bundled);
    if (blobHash && bundledHash === blobHash) {
      return bundled;
    }
    // After a deploy the bundled file is newer; stale blobs must not win.
    return bundled;
  }
  return bundled || blob;
}

export default async (request) => {
  const url = new URL(request.url);
  const file = url.searchParams.get('file') || '';
  if (!files.has(file)) return new Response('Unbekannter Kalender', { status: 404 });
  try {
    const store = getStore('rsv-live-data');
    const value = await pickCalendarText(store, file);
    if (!value) return new Response('Kalender nicht gefunden', { status: 404 });
    return new Response(value, {
      headers: {
        'content-type': 'text/calendar; charset=utf-8',
        'content-disposition': `inline; filename="${file}"`,
        'cache-control': 'public, max-age=300, must-revalidate',
      },
    });
  } catch (error) {
    console.error('calendar blob error', error);
    return new Response('Kalender momentan nicht erreichbar', { status: 503 });
  }
};
