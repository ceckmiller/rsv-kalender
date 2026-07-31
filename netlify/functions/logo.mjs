const ALLOWED_PROTOCOLS = new Set(['https:']);

export default async (request) => {
  const requestUrl = new URL(request.url);
  const raw = requestUrl.searchParams.get('url');
  if (!raw) return new Response('Logo-URL fehlt', { status: 400 });

  let source;
  try {
    source = new URL(raw);
  } catch {
    return new Response('Ungültige Logo-URL', { status: 400 });
  }
  if (!ALLOWED_PROTOCOLS.has(source.protocol)) {
    return new Response('Nicht erlaubte Logo-URL', { status: 400 });
  }

  try {
    const response = await fetch(source, {
      headers: {
        'user-agent': 'RSV-Eintracht-App/2.1 (+https://rsv-kalender.netlify.app)',
        accept: 'image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5'
      },
      redirect: 'follow'
    });
    if (!response.ok) return new Response('Logo nicht erreichbar', { status: 404 });

    const contentType = response.headers.get('content-type') || 'image/png';
    if (!contentType.toLowerCase().startsWith('image/')) {
      return new Response('Keine Bilddatei', { status: 415 });
    }

    return new Response(response.body, {
      headers: {
        'content-type': contentType,
        'cache-control': 'public, max-age=86400, s-maxage=604800, stale-while-revalidate=2592000',
        'x-content-type-options': 'nosniff'
      }
    });
  } catch (error) {
    console.error('logo proxy error', error);
    return new Response('Logo momentan nicht erreichbar', { status: 503 });
  }
};
