import { useRef, useEffect } from 'react';
import type { SSEEvent } from '../api/types';

interface StreamingViewerProps {
  events: SSEEvent[];
  isStreaming: boolean;
  error: string | null;
}

export default function StreamingViewer({
  events,
  isStreaming,
  error,
}: StreamingViewerProps) {
  const textRef = useRef<HTMLDivElement>(null);

  // Auto-scroll as text arrives
  useEffect(() => {
    if (textRef.current) {
      textRef.current.scrollTop = textRef.current.scrollHeight;
    }
  }, [events]);

  // Extract progress info
  const progressEvent = events
    .filter((e): e is Extract<SSEEvent, { type: 'progress' }> => e.type === 'progress')
    .at(-1);

  // Accumulate text from chunk events
  const fullText = events
    .filter((e): e is Extract<SSEEvent, { type: 'chunk' }> => e.type === 'chunk')
    .map((e) => e.text)
    .join('');

  // Check for completion
  const completeEvent = events.find(
    (e): e is Extract<SSEEvent, { type: 'complete' }> => e.type === 'complete',
  );

  const hasContent = progressEvent || fullText || completeEvent || isStreaming;

  if (!hasContent) {
    return (
      <div className="streaming-viewer">
        <div className="streaming-viewer-empty">
          Your story will appear here as it's written...
        </div>
      </div>
    );
  }

  return (
    <div className="streaming-viewer">
      {isStreaming && progressEvent && (
        <div className="streaming-progress">
          <div className="progress-spinner" />
          <span>
            {progressEvent.stage}: {progressEvent.message}
          </span>
        </div>
      )}

      {fullText && (
        <div className="streaming-text" ref={textRef}>
          {fullText}
          {isStreaming && <span className="typing-cursor" />}
        </div>
      )}

      {completeEvent && (
        <div className="streaming-complete">
          <a
            href={`/story/${completeEvent.id}`}
            className="btn btn-primary"
          >
            Read Full Story
          </a>
          <span style={{ color: 'var(--text-muted)', alignSelf: 'center', fontSize: '0.85rem' }}>
            {completeEvent.word_count} words
          </span>
        </div>
      )}

      {error && (
        <div className="streaming-error">
          {error}
        </div>
      )}
    </div>
  );
}
