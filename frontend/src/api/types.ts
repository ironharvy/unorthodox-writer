// SSE event types shared across the app
export interface ProgressEvent {
  type: 'progress';
  stage: string;
  message: string;
}

export interface ChunkEvent {
  type: 'chunk';
  text: string;
}

export interface CompleteEvent {
  type: 'complete';
  id: string;
  title: string;
  word_count: number;
  full_text: string;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export type SSEEvent = ProgressEvent | ChunkEvent | CompleteEvent | ErrorEvent;

export interface Story {
  id: string;
  title: string;
  genre: string;
  style: string;
  pov: string;
  word_count: number;
  created_at: string;
  text?: string;
}

export interface User {
  id: string;
  username: string;
  email?: string;
  tier: 'free' | 'paid';
  stories_today: number;
  daily_limit: number;
  stories_saved: number;
  saved_limit: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface GenerateRequest {
  prompt: string;
  genre: string;
  style: string;
  pov: string;
  max_words: number;
}
