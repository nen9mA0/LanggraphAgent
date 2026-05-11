declare const process: {
  cwd(): string;
  env: Record<string, string | undefined>;
};

declare const Buffer: {
  from(data: string | ArrayBuffer | ArrayBufferView): {
    toString(encoding?: string): string;
  };
  concat(chunks: Array<{ toString(encoding?: string): string }>): {
    toString(encoding?: string): string;
  };
  isBuffer(value: unknown): value is { toString(encoding?: string): string };
};

declare var console: {
  log(...args: unknown[]): void;
};

declare var URL: {
  new (url: string, base?: string): { pathname: string };
};

declare module 'node:http' {
  export interface IncomingMessage {
    method?: string;
    url?: string;
    headers: Record<string, string | string[] | undefined>;
    [key: string]: unknown;
    [Symbol.asyncIterator](): AsyncIterator<string | Uint8Array>;
  }

  export interface ServerResponse {
    writeHead(statusCode: number, headers?: Record<string, string>): void;
    end(data?: string | Uint8Array): void;
    write(chunk: string): void;
  }

  export function createServer(
    handler: (req: IncomingMessage, res: ServerResponse) => void
  ): {
    listen(port: number, host: string, callback?: () => void): void;
  };
}

declare module 'node:fs/promises' {
  export function readFile(path: string, encoding: string): Promise<string>;
  export function writeFile(path: string, data: string, encoding: string): Promise<void>;
  export function mkdir(path: string, options?: { recursive?: boolean }): Promise<void>;
}

declare module 'node:fs' {
  export function existsSync(path: string): boolean;
}

declare module 'node:path' {
  export function join(...parts: string[]): string;
  export function dirname(path: string): string;
}
