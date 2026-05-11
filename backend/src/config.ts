import { join } from 'node:path';

export const PORT = Number(process.env.PORT || 8000);
export const HOST = process.env.HOST || '0.0.0.0';
export const DATA_DIR = join(process.cwd(), 'backend', 'data');
export const DATA_FILE = join(DATA_DIR, 'store.json');
