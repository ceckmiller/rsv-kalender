import { getStore } from '@netlify/blobs';

const files = new Set(['rsv-regionalliga.ics', 'rsv-u23.ics', 'rsv-u21.ics', 'rsv-u19.ics']);

export default async (request) => {
  const url = new URL(request.url);
  const file = url.searchParams.get('file') || '';
  if (!files.has(file)) return new Response('Unbekannter Kalender', { status: 404 });
  try {
    const store = getStore('rsv-live-data');
    const value = await store.get(file, { type: 'text' });
    if (!value) return new Response(null, { status: 404 });
    return new Response(value, {
      headers: {
        'content-type': 'text/calendar; charset=utf-8',
        'content-disposition': `inline; filename="${file}"`,
        'cache-control': 'public, max-age=300, stale-while-revalidate=900'
      }
    });
  } catch (error) {
    console.error('calendar blob error', error);
    return new Response('Kalender momentan nicht erreichbar', { status: 503 });
  }
};
