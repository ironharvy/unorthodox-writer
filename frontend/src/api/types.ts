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

export interface StoryBibleCharacter {
  name: string;
  role: string;
  description: string;
}

export interface StoryBibleProtagonist {
  name: string;
  voice: string;
  traits: string;
  flaw: string;
  arc: string;
}

export interface StoryBibleSetting {
  location: string;
  era: string;
  atmosphere: string;
  rules: string;
}

export interface StoryBibleChapterBeat {
  number: number;
  title: string;
  synopsis: string;
  emotional_beat: string;
  must_include: string[];
  ends_on: string;
  word_target: number;
}

export interface StoryBible {
  title: string;
  logline: string;
  pov: string;
  tone: string;
  themes: string[];
  protagonist: StoryBibleProtagonist;
  characters: StoryBibleCharacter[];
  setting: StoryBibleSetting;
  motifs: string[];
  chapters: StoryBibleChapterBeat[];
}

export interface CritiqueIssue {
  chapter: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  category: string;
  issue: string;
  quote?: string;
  fix?: string;
}

export interface CompleteEvent {
  type: 'complete';
  id: string;
  title: string;
  word_count: number;
  full_text: string;
  bible?: StoryBible;
  critique?: CritiqueIssue[];
  revised_chapters?: number[];
  chapter_count?: number;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export interface BibleEvent {
  type: 'bible';
  bible: StoryBible;
}

export interface ChapterCompleteEvent {
  type: 'chapter_complete';
  chapter: number;
  title: string;
  word_count: number;
}

export interface CritiqueEvent {
  type: 'critique';
  issues: CritiqueIssue[];
}

export interface RevisionEvent {
  type: 'revision';
  chapter: number;
  word_count: number;
}

export type SSEEvent =
  | ProgressEvent
  | ChunkEvent
  | CompleteEvent
  | ErrorEvent
  | BibleEvent
  | ChapterCompleteEvent
  | CritiqueEvent
  | RevisionEvent;

export interface Story {
  id: string;
  title: string;
  genre: string;
  style: string;
  pov: string;
  word_count: number;
  created_at: string;
  text?: string;
  bible?: StoryBible;
  critique?: CritiqueIssue[];
  revised_chapters?: number[];
  chapter_count?: number;
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
