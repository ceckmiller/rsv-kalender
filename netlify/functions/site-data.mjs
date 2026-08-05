import { createHash } from 'node:crypto';
import { readFile } from 'node:fs/promises';
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
      return await readFile(path, 'utf8');
    } catch {
      // try next candidate
    }
  }
  return null;
}

async function pickSiteDataText(store) {
  const bundled = await readBundled();
  let blob = null;
  let blobHash = null;
  try {
    blob = await store.get('site-data.json', { type: 'text' });
    blobHash = await store.get('site-data.json.sha256', { type: 'text' });
  } catch {
    // blob store unavailable
  }
  if (bundled && blob) {
    const bundledHash = siteDataHash(bundled);
    if (blobHash && bundledHash === blobHash) {
      return bundled;
    }
    return bundled;
  }
  return bundled || blob;
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
