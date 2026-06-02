import { useRef, useCallback, useEffect, useState } from 'react';
import type { SSEEvent } from '../api/types';
import { streamStory } from '../api/client';

export function useSSE(storyId: string | null) {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef(false);

  const startStream = useCallback(async () => {
    if (!storyId) return;

    abortRef.current = false;
    setIsStreaming(true);
    setError(null);
    setEvents([]);

    try {
      for await (const event of streamStory(storyId)) {
        if (abortRef.current) break;
        setEvents((prev) => [...prev, event]);

        if (event.type === 'complete') {
          setIsStreaming(false);
          return;
        }
        if (event.type === 'error') {
          setError(event.message);
          setIsStreaming(false);
          return;
        }
      }
    } catch (err) {
      if (!abortRef.current) {
        setError(err instanceof Error ? err.message : 'Stream error');
      }
    } finally {
      setIsStreaming(false);
    }
  }, [storyId]);

  const stop = useCallback(() => {
    abortRef.current = true;
    setIsStreaming(false);
  }, []);

  useEffect(() => {
    startStream();
    return () => {
      abortRef.current = true;
    };
  }, [startStream]);

  return { events, isStreaming, error, stop };
}
