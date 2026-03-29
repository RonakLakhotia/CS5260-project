# YTSage — YouTube to Shorts Synthesis Agent

YTSage is an AI agent that takes a YouTube lecture or tech talk URL and produces 2 AI-generated 30-second explainer video shorts for the most important concepts in the video. Each short includes a script with timestamp citations traceable back to the source.

> This product is entirely derived from work conducted as part of the NUS CS5260 course.

## Architecture

```
User pastes YouTube URL
        ↓
Extract + chunk transcript (YouTube Transcript API)
        ↓
Planner Agent — ranks top 3 concepts by importance
        ↓
Script Writer Agent — writes ~30-sec narration script per concept (top 2)
        ↓
Citation Mapper — links each claim to a timestamp in the source video
        ↓
Text-to-Video Agent — generates 2x ~30-sec AI explainer clips (Runway/Kling)
        ↓
Output Page — embedded clips, scripts, and citation links
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| Agent Orchestration | LangGraph |
| LLM | GPT-4o (OpenAI API) |
| Transcript Extraction | youtube-transcript-api |
| Text-to-Video | Runway ML / Kling API |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Caching | File-based (by URL hash) |

## Project Structure

```
project/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── config.py            # Settings from environment variables
│   │   ├── models.py            # Pydantic models + LangGraph state
│   │   ├── routes/
│   │   │   └── api.py           # API endpoints
│   │   ├── agents/
│   │   │   ├── graph.py         # LangGraph state graph
│   │   │   ├── planner.py       # Concept ranking agent
│   │   │   ├── script_writer.py # Script generation agent
│   │   │   ├── citation_mapper.py # Timestamp citation agent
│   │   │   └── video_generator.py # Text-to-video agent
│   │   └── services/
│   │       ├── transcript.py    # YouTube transcript extraction
│   │       └── cache.py         # File-based caching
│   ├── requirements.txt
│   └── .env.example
├── frontend/                    # Next.js app
│   └── src/app/page.tsx         # Landing page
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/process` | Submit a YouTube URL for processing |
| GET | `/api/status/{job_id}` | Poll job status and progress |
| GET | `/api/result/{job_id}` | Get completed results (scripts, citations, videos) |
| POST | `/api/generate-third/{job_id}` | Generate video for the 3rd concept (on-demand) |
| GET | `/health` | Health check |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Backend Setup

```bash
# Navigate to backend
cd backend

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys:
#   OPENAI_API_KEY=sk-...
#   RUNWAY_API_KEY=...

# Run the server
uvicorn app.main:app --reload --port 8000
```

The backend will be running at `http://localhost:8000`. You can verify at `http://localhost:8000/health`.

### Frontend Setup

```bash
# Navigate to frontend
cd frontend

# Install dependencies
npm install

# Run the dev server
npm run dev
```

The frontend will be running at `http://localhost:3000`.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4o | Yes |
| `RUNWAY_API_KEY` | Runway ML API key for video generation | Later (Week 2) |
| `MAX_COST_PER_SESSION_SGD` | Cost limit per session (default: 8.0) | No |
| `CACHE_DIR` | Directory for cached results (default: ./cache) | No |

## Development Roadmap

### Step 1 — Scaffolding (done)
- Git repo, `.gitignore`, project structure
- FastAPI backend skeleton with API endpoints
- LangGraph agent stubs
- Next.js frontend with landing page

### Step 2 — Transcript Extraction
- Fetch + chunk transcripts from YouTube URLs
- Test with a real video

### Step 3 — LangGraph Agents
- Planner Agent (GPT-4o ranks top 3 concepts)
- Script Writer Agent (30-sec scripts for top 2)
- Citation Mapper (timestamp links per claim)
- Wire them into the state graph

### Step 4 — Backend Pipeline
- Run the full graph async from `/api/process`
- Job status tracking + polling via `/api/status`
- Return real results via `/api/result`
- Caching layer to avoid re-processing same URLs

### Step 5 — Frontend Pages
- Results page (2 concept cards with scripts + citation links)
- Processing page (progress indicator while pipeline runs)
- Navigation between landing → processing → results

**Week 1 checkpoint (Steps 1–5):** Paste a YouTube URL → see 2 concept scripts with timestamp citations on a live page.

### Step 6 — Video Generation (Week 2)
- Integrate Runway or Kling API
- Add video generation node to LangGraph
- Cost check before calling API
- Embed generated videos in results page

### Step 7 — Polish + Deploy (Week 3)
- Deploy backend to Railway/Render
- Deploy frontend to Vercel
- Error handling, edge cases
- UI polish
- Pre-generate demo examples as backup
- Prepare presentation

## Cost Constraints

- Max 2 auto-generated videos per submission
- 3rd video only on explicit user request
- All generated results are cached by YouTube URL hash
- Session aborts if estimated cost exceeds SGD 8
