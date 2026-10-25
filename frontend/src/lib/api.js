const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export { API_BASE };

/**
 * Minimal fetch wrapper for the compliance console.
 * Throws on non-2xx with the server's structured error message when present.
 */
export async function api(path, { token, method = 'GET', body, form, signal } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    signal,
    body: form || (body !== undefined ? JSON.stringify(body) : undefined),
  });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!response.ok) {
    throw new Error(`${response.status}: ${data?.error?.message || data?.detail || response.statusText}`);
  }
  return data;
}

/**
 * Download a staff export (for example the advisory application report).
 *
 * Uses the same base URL and bearer token as `api`, but keeps the body as a
 * Blob so a binary or text export is never parsed as JSON. The filename comes
 * from the server's `Content-Disposition` header.
 */
export async function downloadFile(path, { token, fallbackName = 'download' } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = data?.error?.message || data?.detail || message;
    } catch {
      /* body was not JSON; keep the status text */
    }
    throw new Error(`${response.status}: ${message}`);
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = /filename="?([^";]+)"?/i.exec(disposition);
  const filename = match ? match[1] : fallbackName;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
  return filename;
}

const SESSION_KEY = 'astra-session';

export function loadSession() {
  try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); } catch { return null; }
}

export function saveSession(session) {
  if (session) localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  else localStorage.removeItem(SESSION_KEY);
}
