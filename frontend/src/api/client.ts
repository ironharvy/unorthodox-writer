import type { AuthResponse, SSEEvent, Story, User, GenerateRequest } from './types';

const API_BASE = '/api';

function getToken(): string | null {
  return localStorage.getItem('token');
}

function setToken(token: string): void {
  localStorage.setItem('token', token);
}

function clearToken(): void {
  localStorage.removeItem('token');
  localStorage.removeItem('user');
}

function getUser(): User | null {
  const raw = localStorage.getItem('user');
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

function setUser(user: User): void {
  localStorage.setItem('user', JSON.stringify(user));
}

async function apiFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/login';
  }

  return res;
}

// --- Auth ---

export async function register(
  username: string,
  email: string,
  password: string,
): Promise<AuthResponse> {
  const res = await apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Registration failed');
  }
  const data: AuthResponse = await res.json();
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export async function login(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const res = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Login failed');
  }
  const data: AuthResponse = await res.json();
  setToken(data.access_token);
  setUser(data.user);
  return data;
}

export function logout(): void {
  clearToken();
  window.location.href = '/';
}

// --- Stories ---

export async function generateStory(req: GenerateRequest): Promise<Story> {
  const res = await apiFetch('/stories/generate', {
    method: 'POST',
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Generation failed');
  }
  return res.json();
}

export async function getStories(): Promise<Story[]> {
  const res = await apiFetch('/stories');
  if (!res.ok) throw new Error('Failed to fetch stories');
  return res.json();
}

export async function getStory(id: string): Promise<Story> {
  const res = await apiFetch(`/stories/${id}`);
  if (!res.ok) throw new Error('Failed to fetch story');
  return res.json();
}

export async function deleteStory(id: string): Promise<void> {
  const res = await apiFetch(`/stories/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete story');
}

// --- SSE ---

export async function* streamStory(
  storyId: string,
): AsyncGenerator<SSEEvent, void, undefined> {
  const token = getToken();
  const url = `${API_BASE}/stories/${storyId}/stream`;

  const res = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Stream failed');
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') return;
          try {
            const parsed = JSON.parse(data) as SSEEvent;
            yield parsed;
          } catch {
            // skip unparseable lines
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// --- User / Account ---

export async function getUserProfile(): Promise<User> {
  const res = await apiFetch('/auth/me');
  if (!res.ok) throw new Error('Failed to fetch profile');
  const user: User = await res.json();
  setUser(user);
  return user;
}

export function isAuthenticated(): boolean {
  return !!getToken();
}

export { getToken, setToken, clearToken, getUser, setUser, getToken as __getToken };
