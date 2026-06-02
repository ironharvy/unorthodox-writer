import { useState } from 'react';
import StoryInput from '../components/StoryInput';
import StreamingViewer from '../components/StreamingViewer';
import { useSSE } from '../hooks/useSSE';
import { generateStory } from '../api/client';
import type { GenerateRequest } from '../api/types';

export default function Creator() {
  const [storyId, setStoryId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [maxWords, setMaxWords] = useState(1000);
  const { events, isStreaming, error, stop } = useSSE(storyId);
  const usesNovelPipeline = maxWords > 2000;

  const handleSubmit = async (req: GenerateRequest) => {
    setIsGenerating(true);
    setMaxWords(req.max_words);
    try {
      const story = await generateStory(req);
      setStoryId(story.id);
    } catch (err) {
      console.error('Failed to start generation:', err);
      setIsGenerating(false);
    }
  };

  // Once streaming stops (complete or error), we're no longer generating
  const isDone = !isStreaming && storyId && events.length > 0;

  // Determine if we should show generating state
  const showGenerating = isGenerating || isStreaming;

  return (
    <div className="creator-page">
      <div className="creator-input-section">
        <h2>Create a Story</h2>
        <StoryInput
          onSubmit={handleSubmit}
          isGenerating={showGenerating}
          onMaxWordsChange={setMaxWords}
        />
        {usesNovelPipeline && (
          <div className="novel-mode-indicator">
            <strong>Novel pipeline enabled</strong>
            <span>
              This request will generate a story bible, chapter drafts, editorial notes,
              and a revision pass.
            </span>
          </div>
        )}
        {isDone && (
          <div style={{ marginTop: 16 }}>
            <button
              onClick={() => {
                stop();
                setStoryId(null);
                setIsGenerating(false);
              }}
              className="btn btn-secondary"
            >
              Write Another
            </button>
          </div>
        )}
      </div>

      <div className="creator-viewer-section">
        <StreamingViewer
          events={events}
          isStreaming={isStreaming}
          error={error}
        />
      </div>
    </div>
  );
}
