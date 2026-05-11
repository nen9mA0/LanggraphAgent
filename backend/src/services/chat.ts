import type { IncomingMessage, ServerResponse } from 'node:http';
export function chatResponse(model: string) {
  return {
    id: `chatcmpl-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [
      {
        index: 0,
        message: { role: 'assistant', content: 'This is a minimal backend response.' },
        finish_reason: 'stop',
      },
    ],
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
  };
}

export function paramsResponse() {
  return {
    temperature: { type: 'number', min: 0, max: 2, default: 0.7 },
    topP: { type: 'number', min: 0, max: 1, default: 1 },
    frequencyPenalty: { type: 'number', min: 0, max: 2, default: 0 },
    presencePenalty: { type: 'number', min: 0, max: 2, default: 0 },
    maxTokens: { type: 'number', min: 1, max: 8192, default: 1000 },
  };
}

export function validateKeyResponse(apiKey?: string) {
  const valid = Boolean(apiKey?.trim());
  return {
    valid,
    message: valid ? 'API key is valid' : 'API key is required',
  };
}

export async function streamChat(req: IncomingMessage, res: ServerResponse, model: string) {
  res.writeHead(200, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Accept, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,HEAD,OPTIONS',
    'Content-Type': 'text/event-stream; charset=utf-8',
    Connection: 'keep-alive',
    'Cache-Control': 'no-cache',
  });
  (res as ServerResponse & { flushHeaders?: () => void }).flushHeaders?.();
  const text = 'This is a minimal backend response.';
  const chunkId = `chatcmpl-${Date.now()}`;
  for (const chunk of [text.slice(0, 10), text.slice(10, 20), text.slice(20)]) {
    res.write(
      `data: ${JSON.stringify({
        choices: [{ delta: { content: chunk }, index: 0, finish_reason: null }],
        model,
        created: Math.floor(Date.now() / 1000),
        id: chunkId,
        object: 'chat.completion.chunk',
      })}\n\n`
    );
  }
  res.write('data: [DONE]\n\n');
  res.end();
}
