import { getStore } from '@netlify/blobs';

async function readStatic(path) {
  const base = process.env.URL || 'https://rsv-kalender.netlify.app';
  try {
    const res = await fetch(new URL(path, base));
    if (!res.ok) return null;
    return await res.text();
  } catch {
    return null;
  }
}

export default async () => {
  try {
    const store = getStore('rsv-live-data');
    let value = await store.get('site-data.json', { type: 'text' });
    if (!value) {
      value = await readStatic('/site-data.json');
    }
    if (!value) {
      return new Response(null, { status: 404 });
    }
    return new Response(value, {
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'public, max-age=300, stale-while-revalidate=900'
      }
    });
  } catch (error) {
    console.error('site-data blob error', error);
    return new Response(null, { status: 503 });
  }
};
