import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getStories, getUser } from '../api/client';
import type { Story } from '../api/types';

export default function Library() {
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const user = getUser();
  const isFree = user?.tier === 'free';
  const savedLimit = user?.saved_limit || 3;
  const savedCount = stories.length;

  useEffect(() => {
    getStories()
      .then(setStories)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <div className="library-header">
        <h1>Your Library</h1>
        <Link to="/create" className="btn btn-primary">
          New Story
        </Link>
      </div>

      {loading && (
        <div className="library-empty">
          <p>Loading stories...</p>
        </div>
      )}

      {error && (
        <div className="library-empty">
          <p>Error: {error}</p>
        </div>
      )}

      {!loading && !error && stories.length === 0 && (
        <div className="library-empty">
          <h3>No stories yet</h3>
          <p>Start writing your first story!</p>
          <Link to="/create" className="btn btn-primary" style={{ marginTop: 16 }}>
            Create Story
          </Link>
        </div>
      )}

      {stories.length > 0 && (
        <div className="story-grid">
          {stories.map((story) => (
            <Link
              key={story.id}
              to={`/story/${story.id}`}
              className="card story-card"
              style={{ textDecoration: 'none', color: 'inherit' }}
            >
              <h3>{story.title || 'Untitled'}</h3>
              <div className="meta">
                <span>{story.genre}</span>
                <span>{story.word_count} words</span>
                <span>{new Date(story.created_at).toLocaleDateString()}</span>
              </div>
              {story.text && (
                <div className="excerpt">
                  {story.text.slice(0, 200)}
                  {story.text.length > 200 ? '...' : ''}
                </div>
              )}
            </Link>
          ))}
        </div>
      )}

      {isFree && savedCount >= savedLimit && (
        <div className="library-limit">
          {savedCount}/{savedLimit} stories saved —{' '}
          <Link to="/account">upgrade for unlimited</Link>
        </div>
      )}
    </div>
  );
}
