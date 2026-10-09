import { request as httpRequest } from 'node:http';
import { request as httpsRequest } from 'node:https';
import { Readable } from 'node:stream';
import type { NextRequest } from 'next/server';

// Local development uses this same-origin adapter. In Docker, Nginx sends /api
// directly to FastAPI. Preserve Host/Origin so the backend's CSRF check still runs.
async function forward(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  if (path.some((segment) => segment === '..' || segment.includes('/') || segment.includes('\\')))
    return new Response(null, { status: 400 });
  const maximum = 40 * 1024 * 1024;
  if (Number(request.headers.get('content-length')) > maximum)
    return new Response(null, { status: 413 });
  const body = request.method === 'POST' ? await request.arrayBuffer() : undefined;
  if (body && body.byteLength > maximum) return new Response(null, { status: 413 });
  const headers = new Headers();
  for (const name of ['host', 'origin', 'cookie', 'content-type', 'x-ascentiq-request']) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set('x-forwarded-proto', request.nextUrl.protocol.replace(':', ''));
  const base = process.env.BACKEND_INTERNAL_URL ?? process.env.DEV_API_URL ?? 'http://api:8788';
  try {
    const destination = new URL(
      `${base}/api/${path.map(encodeURIComponent).join('/')}${request.nextUrl.search}`,
    );
    const send = destination.protocol === 'https:' ? httpsRequest : httpRequest;
    return await new Promise<Response>((resolve, reject) => {
      const upstream = send(
        destination,
        {
          method: request.method,
          headers: Object.fromEntries(headers),
          signal: AbortSignal.any([request.signal, AbortSignal.timeout(210_000)]),
        },
        (incoming) => {
          const outgoing = new Headers();
          for (let index = 0; index < incoming.rawHeaders.length; index += 2)
            outgoing.append(incoming.rawHeaders[index], incoming.rawHeaders[index + 1]);
          for (const name of ['transfer-encoding', 'connection']) outgoing.delete(name);
          outgoing.set('Cache-Control', 'private, no-store');
          resolve(
            new Response(Readable.toWeb(incoming) as ReadableStream<Uint8Array>, {
              status: incoming.statusCode ?? 502,
              headers: outgoing,
            }),
          );
        },
      );
      upstream.on('error', reject);
      upstream.end(body ? Buffer.from(body) : undefined);
    });
  } catch {
    return Response.json(
      { detail: 'API indisponível. Verifique o backend e tente novamente.' },
      { status: 502, headers: { 'Cache-Control': 'private, no-store' } },
    );
  }
}
export const GET = forward;
export const POST = forward;
