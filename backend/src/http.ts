import type { IncomingMessage, ServerResponse } from 'node:http';

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'HEAD' | 'OPTIONS';

export function send(res: ServerResponse, status: number, body?: unknown, headers: Record<string, string> = {}) {
  res.writeHead(status, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,HEAD,OPTIONS',
    ...headers,
  });
  if (body === undefined || body === null) {
    res.end();
    return;
  }
  if (typeof body === 'string') {
    res.end(body);
    return;
  }
  res.end(JSON.stringify(body));
}

export function notFound(res: ServerResponse) {
  send(res, 404, { detail: 'Not found' }, { 'Content-Type': 'application/json' });
}

export function parseUrl(req: IncomingMessage) {
  return new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
}

export async function readJson(req: IncomingMessage) {
  const chunks: Array<{ toString(encoding?: string): string }> = [];
  const iterable = req as unknown as AsyncIterable<Uint8Array | string>;
  for await (const chunk of iterable) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  if (!chunks.length) return undefined;
  const text = Buffer.concat(chunks).toString('utf8');
  return text ? JSON.parse(text) : undefined;
}

export function health(_req: IncomingMessage, res: ServerResponse) {
  send(res, 200, { status: 'ok' }, { 'Content-Type': 'application/json' });
}

export function listResponse<T>(res: ServerResponse, items: T[]) {
  send(res, 200, items, { 'Content-Type': 'application/json' });
}
