import { useState } from 'react';
import StoryInput from '../components/StoryInput';
import StreamingViewer from '../components/StreamingViewer';
import { useSSE } from '../hooks/useSSE';
import { generateStory } from '../api/client';
import type { GenerateRequest } from '../api/types';

export default function Creator() {
  const [storyId, setStoryId] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const { events, isStreaming, error, stop } = useSSE(storyId);

  const handleSubmit = async (req: GenerateRequest) => {
    setIsGenerating(true);
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
        />
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
