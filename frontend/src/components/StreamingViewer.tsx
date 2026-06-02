import { useRef, useEffect } from 'react';
import { Link } from 'react-router-dom';
import type { CritiqueIssue, SSEEvent, StoryBible } from '../api/types';

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

  const bibleEvent = events.find(
    (e): e is Extract<SSEEvent, { type: 'bible' }> => e.type === 'bible',
  );
  const bible = completeEvent?.bible ?? bibleEvent?.bible;

  const chapterEvents = events.filter(
    (e): e is Extract<SSEEvent, { type: 'chapter_complete' }> => e.type === 'chapter_complete',
  );
  const critiqueEvent = events.find(
    (e): e is Extract<SSEEvent, { type: 'critique' }> => e.type === 'critique',
  );
  const critique = completeEvent?.critique ?? critiqueEvent?.issues;
  const revisionEvents = events.filter(
    (e): e is Extract<SSEEvent, { type: 'revision' }> => e.type === 'revision',
  );

  const chapterCount = completeEvent?.chapter_count ?? bible?.chapters.length ?? chapterEvents.length;
  const storyState = completeEvent
    ? {
        id: completeEvent.id,
        title: completeEvent.title,
        word_count: completeEvent.word_count,
        text: completeEvent.full_text,
        bible,
        critique,
        revised_chapters: completeEvent.revised_chapters,
        chapter_count: completeEvent.chapter_count,
      }
    : undefined;

  const hasContent =
    progressEvent ||
    fullText ||
    completeEvent ||
    bible ||
    chapterEvents.length > 0 ||
    critique ||
    revisionEvents.length > 0 ||
    isStreaming;

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

      {bible && <StoryBiblePanel bible={bible} />}

      {chapterEvents.length > 0 && (
        <div className="novel-panel">
          <h3>Chapter Drafts</h3>
          <div className="chapter-progress">
            <div className="chapter-progress-track">
              <div
                className="chapter-progress-fill"
                style={{
                  width: chapterCount > 0
                    ? `${Math.min(100, (chapterEvents.length / chapterCount) * 100)}%`
                    : '100%',
                }}
              />
            </div>
            <span>
              {chapterEvents.length}/{chapterCount || chapterEvents.length} drafted
            </span>
          </div>
          <ul className="chapter-status-list">
            {chapterEvents.map((chapter) => (
              <li key={`${chapter.chapter}-${chapter.title}`}>
                Chapter {chapter.chapter}/{chapterCount || chapter.chapter} drafted:{' '}
                <strong>{chapter.title}</strong> ({chapter.word_count.toLocaleString()} words)
              </li>
            ))}
          </ul>
        </div>
      )}

      {critique && <CritiquePanel issues={critique} />}

      {revisionEvents.length > 0 && (
        <div className="novel-panel">
          <h3>Revision Pass</h3>
          <ul className="chapter-status-list">
            {revisionEvents.map((revision) => (
              <li key={`${revision.chapter}-${revision.word_count}`}>
                Chapter {revision.chapter} revised ({revision.word_count.toLocaleString()} words)
              </li>
            ))}
          </ul>
        </div>
      )}

      {completeEvent && (
        <div className="streaming-complete">
          <Link
            to={`/story/${completeEvent.id}`}
            state={{ story: storyState }}
            className="btn btn-primary"
          >
            Read Full Story
          </Link>
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

function StoryBiblePanel({ bible }: { bible: StoryBible }) {
  return (
    <details className="novel-panel" open>
      <summary>Story Bible</summary>
      <div className="bible-summary">
        <h3>{bible.title}</h3>
        <p>{bible.logline}</p>
        <div className="bible-meta">
          <span>{bible.pov}</span>
          <span>{bible.tone}</span>
          {bible.themes.map((theme) => (
            <span key={theme}>{theme}</span>
          ))}
        </div>
      </div>

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

      {bible.motifs.length > 0 && (
        <section className="novel-section">
          <h4>Motifs</h4>
          <div className="bible-meta">
            {bible.motifs.map((motif) => (
              <span key={motif}>{motif}</span>
            ))}
          </div>
        </section>
      )}

      {bible.chapters.length > 0 && (
        <section className="novel-section">
          <h4>Chapter Beat Sheet</h4>
          <ol className="beat-list">
            {bible.chapters.map((chapter) => (
              <li key={chapter.number}>
                <strong>{chapter.title}</strong>
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
    </details>
  );
}

function CritiquePanel({ issues }: { issues: CritiqueIssue[] }) {
  const groupedIssues = issues.reduce<Record<number, CritiqueIssue[]>>((acc, issue) => {
    acc[issue.chapter] = [...(acc[issue.chapter] ?? []), issue];
    return acc;
  }, {});

  return (
    <div className="novel-panel">
      <h3>Editor's Notes</h3>
      {Object.entries(groupedIssues).map(([chapter, chapterIssues]) => (
        <section className="novel-section" key={chapter}>
          <h4>Chapter {chapter}</h4>
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
