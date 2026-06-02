import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getStory, deleteStory } from '../api/client';
import type { Story } from '../api/types';

export default function StoryView() {
  const { id } = useParams<{ id: string }>();
  const [story, setStory] = useState<Story | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);

  useEffect(() => {
    if (!id) return;
    getStory(id)
      .then(setStory)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = async () => {
    if (!id) return;
    try {
      await deleteStory(id);
      setDeleted(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    }
  };

  if (deleted) {
    return (
      <div className="story-view">
        <p style={{ color: 'var(--text-muted)', marginBottom: 16 }}>
          Story deleted.
        </p>
        <Link to="/library" className="btn btn-primary">
          Back to Library
        </Link>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="story-view">
        <p style={{ color: 'var(--text-muted)' }}>Loading story...</p>
      </div>
    );
  }

  if (error || !story) {
    return (
      <div className="story-view">
        <p style={{ color: 'var(--danger)' }}>{error || 'Story not found'}</p>
        <Link to="/library">Back to Library</Link>
      </div>
    );
  }

  return (
    <div className="story-view">
      <Link to="/library" className="back-link">
        ← Back to Library
      </Link>

      <h1>{story.title || 'Untitled'}</h1>

      <div className="story-meta">
        <span>{story.genre}</span>
        <span>{story.word_count} words</span>
        <span>{new Date(story.created_at).toLocaleDateString()}</span>
      </div>

      <div className="story-body">
        {story.text || 'No content available.'}
      </div>

      <div className="story-actions">
        <Link to="/library" className="btn btn-secondary">
          Back to Library
        </Link>
        <button onClick={handleDelete} className="btn btn-danger btn-sm">
          Delete Story
        </button>
      </div>
    </div>
  );
}
