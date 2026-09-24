import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
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
      const text = await readFile(path, 'utf8');
      const info = await stat(path);
      return { text, mtimeMs: info.mtimeMs };
    } catch {
      // try next candidate
    }
  }
  return null;
}

async function readBlob(store, file) {
  try {
    const result = await store.getWithMetadata(file, { type: 'text' });
    if (!result?.data) return null;
    const updatedAt = Date.parse(result.metadata?.updatedAt || '');
    return { text: result.data, updatedAt: Number.isFinite(updatedAt) ? updatedAt : 0 };
  } catch {
    try {
      const text = await store.get(file, { type: 'text' });
      return text ? { text, updatedAt: 0 } : null;
    } catch {
      return null;
    }
  }
}

async function pickCalendarText(store, file) {
  const bundled = await readBundled(file);
  const blob = await readBlob(store, file);
  if (bundled && blob) {
    if (sha256(bundled.text) === sha256(blob.text)) return blob.text;
    // Blobs are written by the calendar workflow without a deploy.
    // A newer bundled file (fresh deploy whose blob sync failed) still wins.
    if (blob.updatedAt > bundled.mtimeMs) return blob.text;
    return bundled.text;
  }
  return blob?.text || bundled?.text || null;
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
