import { useState } from 'react';
import type { GenerateRequest } from '../api/types';
import { getUser } from '../api/client';

interface StoryInputProps {
  onSubmit: (req: GenerateRequest) => void;
  isGenerating: boolean;
}

const GENRES = [
  'Fantasy',
  'Sci-Fi',
  'Horror',
  'Mystery',
  'Romance',
  'Adventure',
  'Literary',
  'Thriller',
  'Historical',
  'Comedy',
];

const STYLES = [
  'Descriptive',
  'Minimalist',
  'Cinematic',
  'Whimsical',
  'Gritty',
  'Poetic',
  'Conversational',
  'Academic',
];

const POVS = [
  'First Person',
  'Second Person',
  'Third Person Limited',
  'Third Person Omniscient',
];

export default function StoryInput({ onSubmit, isGenerating }: StoryInputProps) {
  const user = getUser();
  const isFree = user?.tier === 'free';
  const maxWords = isFree ? 500 : 5000;

  const [prompt, setPrompt] = useState('');
  const [genre, setGenre] = useState('Fantasy');
  const [style, setStyle] = useState('Descriptive');
  const [pov, setPov] = useState('Third Person Limited');
  const [wordCount, setWordCount] = useState(isFree ? 500 : 1000);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isGenerating) return;
    onSubmit({
      prompt: prompt.trim(),
      genre,
      style,
      pov,
      max_words: wordCount,
    });
  };

  return (
    <form className="story-input-form" onSubmit={handleSubmit}>
      <div className="form-group">
        <label htmlFor="prompt">Your idea, lyric, or scenario</label>
        <textarea
          id="prompt"
          placeholder="e.g., A lighthouse keeper discovers a message in a bottle from someone who claims to be their future self..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={isGenerating}
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label htmlFor="genre">Genre</label>
          <select
            id="genre"
            value={genre}
            onChange={(e) => setGenre(e.target.value)}
            disabled={isGenerating}
          >
            {GENRES.map((g) => (
              <option key={g} value={g}>{g}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="style">Style</label>
          <select
            id="style"
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            disabled={isGenerating}
          >
            {STYLES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="pov">Point of View</label>
          <select
            id="pov"
            value={pov}
            onChange={(e) => setPov(e.target.value)}
            disabled={isGenerating}
          >
            {POVS.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-group">
        <label htmlFor="wordCount">
          Word Count: <strong>{wordCount}</strong>
          {isFree && (
            <span className="word-count-display">
              {' '}(Free tier max: {maxWords})
            </span>
          )}
        </label>
        <input
          id="wordCount"
          type="range"
          min={100}
          max={maxWords}
          step={50}
          value={wordCount}
          onChange={(e) => setWordCount(Number(e.target.value))}
          disabled={isGenerating}
        />
      </div>

      <button
        type="submit"
        className="btn btn-primary btn-lg"
        disabled={!prompt.trim() || isGenerating}
        style={{ marginTop: 8 }}
      >
        {isGenerating ? 'Generating...' : 'Generate Story'}
      </button>
    </form>
  );
}
