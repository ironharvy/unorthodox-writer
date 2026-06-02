import { useEffect, useState } from 'react';
import { useParams, Link, useLocation } from 'react-router-dom';
import { getStory, deleteStory } from '../api/client';
import type { CritiqueIssue, Story, StoryBible } from '../api/types';

type StoryTab = 'story' | 'bible' | 'notes';

interface StoryLocationState {
  story?: Partial<Story>;
}

export default function StoryView() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const streamedStory = (location.state as StoryLocationState | null)?.story;
  const [story, setStory] = useState<Story | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleted, setDeleted] = useState(false);
  const [activeTab, setActiveTab] = useState<StoryTab>('story');

  useEffect(() => {
    if (!id) return;
    getStory(id)
      .then((fetchedStory) => {
        setStory({
          ...fetchedStory,
          text: fetchedStory.text ?? streamedStory?.text,
          bible: fetchedStory.bible ?? streamedStory?.bible,
          critique: fetchedStory.critique ?? streamedStory?.critique,
          revised_chapters: fetchedStory.revised_chapters ?? streamedStory?.revised_chapters,
          chapter_count: fetchedStory.chapter_count ?? streamedStory?.chapter_count,
        });
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load'))
      .finally(() => setLoading(false));
  }, [id, streamedStory]);

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

      <div className="story-tabs" role="tablist" aria-label="Story sections">
        <button
          type="button"
          className={activeTab === 'story' ? 'active' : ''}
          onClick={() => setActiveTab('story')}
        >
          Story
        </button>
        <button
          type="button"
          className={activeTab === 'bible' ? 'active' : ''}
          onClick={() => setActiveTab('bible')}
        >
          Bible
        </button>
        <button
          type="button"
          className={activeTab === 'notes' ? 'active' : ''}
          onClick={() => setActiveTab('notes')}
        >
          Editor's Notes
        </button>
      </div>

      {activeTab === 'story' && (
        <div className="story-body">
          {story.text || 'No content available.'}
        </div>
      )}

      {activeTab === 'bible' && <BibleTab bible={story.bible} />}

      {activeTab === 'notes' && (
        <NotesTab
          issues={story.critique}
          revisedChapters={story.revised_chapters}
        />
      )}

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

function BibleTab({ bible }: { bible?: StoryBible }) {
  if (!bible) {
    return <EmptyTab message="No story bible is available for this story." />;
  }

  return (
    <div className="story-tab-panel">
      <section className="novel-section">
        <h3>{bible.title}</h3>
        <p>{bible.logline}</p>
        <div className="bible-meta">
          <span>{bible.pov}</span>
          <span>{bible.tone}</span>
          {bible.themes.map((theme) => (
            <span key={theme}>{theme}</span>
          ))}
        </div>
      </section>

      <div className="novel-grid">
        <section className="novel-card">
          <h4>Protagonist</h4>
          <p><strong>{bible.protagonist.name}</strong></p>
          <p>Voice: {bible.protagonist.voice}</p>
          <p>Traits: {bible.protagonist.traits}</p>
          <p>Flaw: {bible.protagonist.flaw}</p>
          <p>Arc: {bible.protagonist.arc}</p>
        </section>

        <section className="novel-card">
          <h4>Setting</h4>
          <p>Location: {bible.setting.location}</p>
          <p>Era: {bible.setting.era}</p>
          <p>Atmosphere: {bible.setting.atmosphere}</p>
          <p>Rules: {bible.setting.rules}</p>
        </section>
      </div>

      {bible.characters.length > 0 && (
        <section className="novel-section">
          <h4>Characters</h4>
          <ul className="compact-list">
            {bible.characters.map((character) => (
              <li key={`${character.name}-${character.role}`}>
                <strong>{character.name}</strong>, {character.role}: {character.description}
              </li>
            ))}
          </ul>
        </section>
      )}

      {bible.chapters.length > 0 && (
        <section className="novel-section">
          <h4>Beat Sheet</h4>
          <ol className="beat-list">
            {bible.chapters.map((chapter) => (
              <li key={chapter.number}>
                <strong>{chapter.number}. {chapter.title}</strong>
                <p>{chapter.synopsis}</p>
                <small>
                  {chapter.emotional_beat} - Ends on {chapter.ends_on} -{' '}
                  {chapter.word_target.toLocaleString()} words
                </small>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function NotesTab({
  issues,
  revisedChapters,
}: {
  issues?: CritiqueIssue[];
  revisedChapters?: number[];
}) {
  if ((!issues || issues.length === 0) && (!revisedChapters || revisedChapters.length === 0)) {
    return <EmptyTab message="No editor's notes are available for this story." />;
  }

  const groupedIssues = (issues ?? []).reduce<Record<number, CritiqueIssue[]>>((acc, issue) => {
    acc[issue.chapter] = [...(acc[issue.chapter] ?? []), issue];
    return acc;
  }, {});

  return (
    <div className="story-tab-panel">
      {revisedChapters && revisedChapters.length > 0 && (
        <section className="novel-section">
          <h3>Revision Summary</h3>
          <p>Revised chapters: {revisedChapters.join(', ')}</p>
        </section>
      )}

      {Object.entries(groupedIssues).map(([chapter, chapterIssues]) => (
        <section className="novel-section" key={chapter}>
          <h3>Chapter {chapter}</h3>
          <ul className="critique-list">
            {chapterIssues.map((issue) => (
              <li key={`${issue.chapter}-${issue.category}-${issue.issue}`}>
                <span className={`severity-badge ${issue.severity}`}>{issue.severity}</span>
                <strong>{issue.category}</strong>
                <p>{issue.issue}</p>
                {issue.quote && <blockquote>{issue.quote}</blockquote>}
                {issue.fix && <p className="critique-fix">Fix: {issue.fix}</p>}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function EmptyTab({ message }: { message: string }) {
  return <div className="story-tab-empty">{message}</div>;
}
