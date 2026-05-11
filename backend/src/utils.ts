export const clone = <T>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export const sanitizeIdentifier = (value: string) =>
  value
    .replace(/[^a-zA-Z0-9_]/g, '_')
    .replace(/^(\d)/, '_$1')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '') || 'flow';

export const toPascalCase = (value: string) =>
  sanitizeIdentifier(value)
    .split('_')
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join('') || 'Flow';

export const now = () => new Date().toISOString();

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

export const stringifyValue = (value: unknown): string => {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return '';
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
};

export const parseInitialValue = (value: unknown): unknown => {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'string') return value;

  const trimmed = value.trim();
  if (!trimmed || trimmed === 'None' || trimmed === 'null') return null;
  if (trimmed === '[]' || trimmed === '{}') return JSON.parse(trimmed);
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (/^-?\d+(?:\.\d+)?$/.test(trimmed)) return Number(trimmed);

  if ((trimmed.startsWith('[') && trimmed.endsWith(']')) || (trimmed.startsWith('{') && trimmed.endsWith('}'))) {
    try {
      return JSON.parse(trimmed);
    } catch {
      return value;
    }
  }

  return value;
};
