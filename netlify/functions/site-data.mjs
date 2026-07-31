import { getStore } from '@netlify/blobs';

export default async () => {
  try {
    const store = getStore('rsv-live-data');
    const value = await store.get('site-data.json', { type: 'text' });
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
