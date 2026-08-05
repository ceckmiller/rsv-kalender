import { getStore } from '@netlify/blobs';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

const files = new Set([
  'rsv-regionalliga.ics',
  'rsv-u23.ics',
  'rsv-u21.ics',
  'rsv-u19.ics',
  'hertha-bsc.ics',
]);

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

export default async (request) => {
  const url = new URL(request.url);
  const file = url.searchParams.get('file') || '';
  if (!files.has(file)) return new Response('Unbekannter Kalender', { status: 404 });
  try {
    const store = getStore('rsv-live-data');
    let value = await store.get(file, { type: 'text' });
    if (!value) {
      value = await readBundled(file);
    }
    if (!value) return new Response('Kalender nicht gefunden', { status: 404 });
    return new Response(value, {
      headers: {
        'content-type': 'text/calendar; charset=utf-8',
        'content-disposition': `inline; filename="${file}"`,
        'cache-control': 'public, max-age=300, stale-while-revalidate=900',
      },
    });
  } catch (error) {
    console.error('calendar blob error', error);
    return new Response('Kalender momentan nicht erreichbar', { status: 503 });
  }
};
