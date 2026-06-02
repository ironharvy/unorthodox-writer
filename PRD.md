# Unorthodox Writer — PRD

## Vision
A web service that transforms free-form user input (ideas, lyrics, prompts, fragments) into coherent, interesting stories. Think "Midjourney for text" or "Suno for stories." The core differentiator: any input → a real story, not just a completion. Two tiers: free (local models, short stories, basic controls) and paid (premium APIs, long-form up to novel-length, full creative controls).

## Architecture

```
┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  React SPA   │────▶│  FastAPI Backend  │────▶│  Story Engine   │
│  (Vite)      │     │  (port 8000)      │     │  (orchestration) │
│              │◀────│                   │◀────│                 │
└──────────────┘     │  - /api/stories   │     │ - Free: Ollama   │
                     │  - /api/auth      │     │ - Paid: Claude   │
                     │  - /api/tiers     │     │        / GPT     │
                     └────────┬──────────┘     └─────────────────┘
                              │
                     ┌────────▼──────────┐
                     │     SQLite DB     │
                     │  users, stories,  │
                     │  tier limits      │
                     └───────────────────┘
```

### Tech Stack
- **Frontend:** React 18 + Vite + TypeScript, vanilla CSS (no framework bloat for Pi)
- **Backend:** Python 3.11 + FastAPI + SQLAlchemy + SQLite
- **Story Engine:** Python package — model-agnostic story generation pipeline
- **AI Backends:**
  - Free tier: Ollama (local, open-weight models via `http://192.168.1.20:11434`)
  - Paid tier: Anthropic Claude API + OpenAI GPT API

### Data Flow
1. User submits input (text) + selects controls (genre, length, style, POV)
2. Backend validates tier limits (free: max 500 words, paid: up to 50,000+)
3. Story Engine builds a prompt pipeline: expand → outline → draft → polish
4. Engine calls appropriate AI backend, streams progress via SSE
5. Story saved to DB, returned to frontend

### Tier Differentiation

| Feature | Free | Paid |
|---------|------|------|
| Model | Ollama (local) | Claude 4 / GPT-5 |
| Max story length | 500 words | 50,000+ words (novel) |
| Genre selection | 3 basic genres | Full genre library |
| Style controls | None | Tone, POV, pacing, structure |
| Export formats | Plain text | Markdown, PDF, EPUB |
| Story history | Last 3 stories | Unlimited history |
| Rate limit | 5 stories/day | Unlimited |

## Workstream Decomposition

### WS1: Backend (FastAPI server)
- **Deliverable:** Working FastAPI app with all endpoints, DB models, auth, tier enforcement
- **Files:** `backend/` directory
- **Endpoints:** POST /api/stories (create), GET /api/stories/{id} (read), GET /api/stories (list), GET /api/stories/{id}/stream (SSE), POST /api/auth/register, POST /api/auth/login, GET /api/tiers/status

### WS2: Story Engine (generation pipeline)
- **Deliverable:** Python package that takes input + controls → full story via multi-stage pipeline
- **Files:** `engine/` directory
- **Pipeline:** Expand input → Build outline → Draft sections → Polish → Assemble
- **Must be model-agnostic** — same pipeline, different backends per tier

### WS3: Frontend (React SPA)
- **Deliverable:** Full React app with story creation flow, library, tier management
- **Files:** `frontend/` directory
- **Pages:** Home/landing, Story Creator (input form + streaming viewer), Story Library, Account/Tier management
- **Must consume SSE from backend for live story generation**

## API Contracts

### POST /api/stories
```json
// Request
{
  "prompt": "string (user's free-form input)",
  "genre": "string | null",
  "style": "string | null",
  "max_words": "integer | null",
  "pov": "string | null"
}
// Response: { "id": "uuid", "status": "generating", "title": "string" }
```

### GET /api/stories/{id}/stream (SSE)
```
event: progress
data: {"stage": "outline", "message": "Building story structure..."}

event: chunk
data: {"text": "It was a dark and stormy night..."}

event: complete
data: {"id": "uuid", "title": "...", "word_count": 1234, "full_text": "..."}

event: error
data: {"message": "Generation failed: ..."}
```

### GET /api/tiers/status
```json
{"tier": "free", "stories_today": 2, "limit": 5, "stories_saved": 15, "max_saved": 3}
```

## Success Criteria
1. ✅ User submits free-form text → receives a coherent story (not a ramble)
2. ✅ Story generates with live streaming — user sees it being written
3. ✅ Free tier enforced: word cap, rate limit, story count limit
4. ✅ Paid tier delivers novel-length output via premium APIs
5. ✅ Frontend is clean, responsive, no console errors
6. ✅ All three workstreams integrate: frontend → backend → engine → AI → back
7. ✅ Single command to start: `make dev` or `docker-compose up`

## Project Structure
```
unorthodox-writer/
├── backend/
│   ├── main.py           # FastAPI app entry
│   ├── models.py         # SQLAlchemy models
│   ├── routes/
│   │   ├── stories.py    # Story CRUD + SSE
│   │   ├── auth.py       # Register/login
│   │   └── tiers.py      # Tier status
│   ├── middleware/
│   │   └── tier.py       # Tier enforcement
│   └── requirements.txt
├── engine/
│   ├── __init__.py
│   ├── pipeline.py       # Multi-stage story pipeline
│   ├── backends/
│   │   ├── ollama.py     # Free tier backend
│   │   ├── claude.py     # Paid tier backend
│   │   └── openai.py     # Paid tier backend
│   └── templates.py      # Genre/style prompt templates
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   ├── Creator.tsx
│   │   │   └── Library.tsx
│   │   ├── components/
│   │   │   ├── StoryInput.tsx
│   │   │   ├── StreamingViewer.tsx
│   │   │   └── TierBadge.tsx
│   │   └── hooks/
│   │       └── useSSE.ts
│   └── package.json
├── Makefile
└── README.md
```
