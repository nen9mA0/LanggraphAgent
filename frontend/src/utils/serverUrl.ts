const DEFAULT_SERVER_URL = 'http://127.0.0.1:8000';

export const getServerUrl = () => {
  if (typeof window !== 'undefined') {
    return (
      window.localStorage.getItem('serverUrl') ||
      import.meta.env.VITE_API_URL ||
      import.meta.env.VITE_API_BASE_URL ||
      DEFAULT_SERVER_URL
    );
  }

  return import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL || DEFAULT_SERVER_URL;
};

export const getApiBaseUrl = () => `${getServerUrl().replace(/\/$/, '')}/api`;

export { DEFAULT_SERVER_URL };
