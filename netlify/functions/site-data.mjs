import { createHash } from 'node:crypto';
import { readFile, stat } from 'node:fs/promises';
import { join } from 'node:path';
import { getStore } from '@netlify/blobs';

function siteDataHash(content) {
  const data = JSON.parse(content);
  delete data.generated_at;
  return createHash('sha256').update(JSON.stringify(data)).digest('hex');
}

async function readBundled() {
  const paths = [
    join(process.cwd(), 'docs', 'site-data.json'),
    join(process.cwd(), 'site-data.json'),
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

async function readBlob(store) {
  try {
    const result = await store.getWithMetadata('site-data.json', { type: 'text' });
    if (!result?.data) return null;
    const updatedAt = Date.parse(result.metadata?.updatedAt || '');
    return { text: result.data, updatedAt: Number.isFinite(updatedAt) ? updatedAt : 0 };
  } catch {
    try {
      const text = await store.get('site-data.json', { type: 'text' });
      return text ? { text, updatedAt: 0 } : null;
    } catch {
      return null;
    }
  }
}

async function pickSiteDataText(store) {
  const bundled = await readBundled();
  const blob = await readBlob(store);
  if (bundled && blob) {
    if (siteDataHash(bundled.text) === siteDataHash(blob.text)) return blob.text;
    if (blob.updatedAt > bundled.mtimeMs) return blob.text;
    return bundled.text;
  }
  return blob?.text || bundled?.text || null;
}

export default async () => {
  try {
    const store = getStore('rsv-live-data');
    const value = await pickSiteDataText(store);
    if (!value) {
      return new Response(null, { status: 404 });
    }
    return new Response(value, {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'public, max-age=300, must-revalidate',
      },
    });
  } catch (error) {
    console.error('site-data blob error', error);
    return new Response(null, { status: 503 });
  }
};
