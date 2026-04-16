# YTSage - YouTube Video Chat + Infographic Synthesis

YTSage is a multi-agent AI system that turns any YouTube video into a conversational assistant. Paste a URL and you can:

1. **Chat with the video** - ask anything; answers are grounded in the transcript with clickable source timestamps that seek the embedded player.
2. **Generate an infographic slideshow** - in the background, a LangGraph pipeline extracts the 3 most important concepts, designs 6 educational infographic slides, and stitches them into a 30-second MP4.
3. **Switch to web search** - toggle the "Web search" button in the chat to answer general questions using Gemini + Google Search grounding with citation links.

> Built for NUS CS5260.

**Live demo**: https://cs-5260-project.vercel.app

## Architecture

```
User pastes a YouTube URL
         |
         v
[Ingestion SSE]
   - yt-dlp metadata
   - Transcript (caption API + Whisper fallback)
   - GPT-4o summary (parallel with chunking)
   - Semantic chunking + OpenAI embeddings -> ChromaDB
   - Create chat session (SQLite)
         |
         +----> redirect to /chat
         |
         v
[LangGraph pipeline (background)]
   ingest -> planner -> script_writer -> video_generator -> END
             GPT-4o     GPT-4o          Nano Banana Pro
                                        + ffmpeg stitch
                                        |
                                        v
                              slideshow.mp4 (1080x1920, 30s)
```

The chat, ingestion, and infographic pipeline all run in parallel. The user can chat with the transcript while the slideshow is still being generated.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Agent orchestration | LangGraph |
| LLM (pipeline + chat) | OpenAI GPT-4o |
| LLM (web search) | Gemini 2.5 Flash with Google Search grounding |
| Image generation | Google Nano Banana Pro (via Replicate) |
| Video stitching | ffmpeg |
| Transcript | youtube-transcript-api + OpenAI Whisper fallback |
| Vector store | ChromaDB (cosine distance) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat persistence | SQLite (aiosqlite, WAL mode) |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind 4 |
| Markdown rendering | react-markdown |
| Deployment (backend) | GCE Ubuntu 22.04 + nginx + Let's Encrypt (sslip.io) |
| Deployment (frontend) | Vercel |

## Features

### Chat with the video
- Streaming token-by-token responses (SSE)
- RAG against transcript chunks; results filtered by cosine distance
- Conversational context: conversational follow-ups ("explain that further") are rewritten into standalone queries before searching
- Conversation history persisted in SQLite with a rolling summary for long sessions
- Up to 3 transcript "Video references" shown under each answer - each has a **Play** button that seeks the embedded YouTube player in place via the iframe API (no tab switches, no state loss)

### Web search toggle
- Gemini 2.5 Flash with `google_search` tool
- Streams the answer with inline markdown + source citations as "Web sources"

### Infographic slideshow
- Runs concurrently with the chat so the user is never blocked
- Subtle pill above the chat input shows live pipeline progress (expandable to see each step, check marks for completed stages)
- Transitions to a green "Slideshow ready" pill when the MP4 is available; clicking opens a floating video player card
- State survives page refreshes and is looked up per-video from SQLite, so any browser / device shows the correct status

### Storage
All three storage systems are linked by `video_id`:
- `yt_{video_id}` ChromaDB collection - transcript chunks + embeddings
- `videos` SQLite table - metadata, slideshow path, pipeline job id
- `./cache/videos/slideshow_{video_id}.mp4` - stitched video file

## API

All `/api/*` endpoints require an `X-API-Key` header (or `?api_key=` query param for media URLs) when `API_KEY` is set in `.env`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingest` | SSE stream: metadata -> transcript -> summary -> embedding -> done |
| GET | `/api/ingest/{video_id}` | Polling fallback for ingestion status |
| POST | `/api/process` | Kick off the LangGraph infographic pipeline |
| GET | `/api/status/{job_id}` | Poll pipeline status |
| GET | `/api/result/{job_id}` | Completed pipeline result |
| GET | `/api/slideshow/video/{video_id}` | Serve slideshow MP4 (survives backend restarts via SQLite lookup) |
| GET | `/api/videos` | List all ingested videos |
| GET | `/api/videos/{video_id}` | Get a video's metadata + slideshow/pipeline status |
| POST | `/api/chat/sessions` | Create a chat session |
| POST | `/api/chat/sessions/{chat_id}/messages` | SSE stream: status -> sources -> tokens -> done |
| GET | `/api/chat/sessions/{chat_id}/messages` | Full message history |
| GET | `/health` | Health check (no auth) |

SSE events the frontend consumes:
- `status` - `searching_transcript`, `reviewing_history`, `searching_web`, `generating`
- `sources` - top 3 transcript chunks with timestamps
- `web_sources` - Gemini grounding citations
- `token` - streaming text chunk
- `done` - final `message_id`
- `error` - failure message

## Project Structure

```
backend/
  app/
    main.py                     # FastAPI, CORS, API-key middleware, lifespan
    core/
      config.py                 # Pydantic settings (env-driven)
      prompts.py                # All LLM system prompts
      logger.py
    models/
      chat.py, ingestion.py, pipeline.py, state.py
    routes/
      chat_sessions.py          # Session chat + web search branch (Gemini)
      chat.py                   # Deprecated stateless chat
      ingestion.py              # SSE ingestion + live-stream rejection
      pipeline.py               # LangGraph job endpoints + video serving
      debug.py
    agents/
      graph.py                  # LangGraph definition
      ingest.py                 # Ingest node (skips if already ingested)
      planner.py                # GPT-4o: top 3 concepts
      script_writer.py          # GPT-4o: 2 infographic prompts per concept
      video_generator.py        # Replicate Nano Banana Pro + ffmpeg stitch
    services/
      transcript.py             # yt-dlp + caption API + Whisper fallback + semantic chunking
      vector_store.py           # ChromaDB wrapper
      metadata.py               # yt-dlp metadata + live-stream rejection
      summary.py                # GPT-4o structured summary
      conversation.py           # Sliding-window history + rolling summary
      chat_store.py             # SQLite sessions/messages/videos
      web_search.py             # Gemini streaming with Google Search grounding
      sse.py                    # SSE helpers
      formatting.py, cache.py, infographic.py
  run.sh, run-prod.sh
  requirements.txt
  .env.example
frontend/
  src/
    app/
      page.tsx                  # Home page - URL input with SSE ingestion progress
      chat/[chatId]/page.tsx    # Main chat UI (video + messages + references + slideshow banner)
      processing/[jobId]/page.tsx
      results/[jobId]/page.tsx
      layout.tsx, globals.css
    lib/api.ts                  # apiFetch + withApiKey helpers
deploy/
  setup-gce.sh                  # One-shot VM bootstrap (python 3.12, ffmpeg, nginx, systemd)
```

## Local Development

### Prerequisites
- Python 3.12 (`brew install python@3.12`)
- Node.js 20+
- ffmpeg (`brew install ffmpeg`)
- API keys: OpenAI, Replicate, Gemini

### Backend

```bash
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit .env with your keys
./run.sh               # runs on :8000 with --reload
```

### Frontend

```bash
cd frontend
npm install
cp .env.example .env.local   # set NEXT_PUBLIC_API_URL
npm run dev                  # runs on :3000
```

### Environment Variables

**backend/.env**

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | OpenAI API key (embeddings, GPT-4o for chat/planner/script writer/summary, Whisper) |
| `REPLICATE_API_TOKEN` | Replicate token (Nano Banana Pro image generation only) |
| `GEMINI_API_KEY` | Google AI Studio API key (web search with Google grounding) |
| `API_KEY` | Optional. If set, all `/api/*` endpoints require `X-API-Key` header or `?api_key=` query param |
| `CORS_ORIGINS` | Comma-separated list of allowed origins. Default `*` |
| `CHROMA_PERSIST_DIR` | ChromaDB path, default `./chroma_db` |
| `CHAT_DB_PATH` | SQLite path, default `./chat.db` |
| `CACHE_DIR` | Video cache path, default `./cache` |
| `LLM_MODEL` | Default `gpt-4o` |
| `EMBEDDING_MODEL` | Default `text-embedding-3-small` |

**frontend/.env.local**

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL, e.g. `http://localhost:8000` |
| `NEXT_PUBLIC_API_KEY` | Must match backend `API_KEY` if set |

## Deployment

### Backend on GCE

Entire VM bootstrap is automated by [`deploy/setup-gce.sh`](deploy/setup-gce.sh):

```bash
# 1. Create the VM (from your local machine)
gcloud compute instances create ytsage-backend \
  --zone=asia-southeast1-b \
  --machine-type=e2-small \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB --boot-disk-type=pd-standard \
  --tags=http-server,https-server

gcloud compute firewall-rules create allow-http  --allow=tcp:80  --target-tags=http-server
gcloud compute firewall-rules create allow-https --allow=tcp:443 --target-tags=https-server

# 2. SSH in, clone, bootstrap
gcloud compute ssh ytsage-backend --zone=asia-southeast1-b
git clone <repo> /opt/ytsage
bash /opt/ytsage/deploy/setup-gce.sh

# 3. Fill in /opt/ytsage/backend/.env
sudo vim /opt/ytsage/backend/.env
sudo systemctl restart ytsage

# 4. HTTPS via Let's Encrypt (sslip.io gives a free domain for your IP)
sudo certbot --nginx -d <ip-with-dashes>.sslip.io
sudo sed -i "s/server_name _;/server_name <ip-with-dashes>.sslip.io;/" /etc/nginx/sites-available/ytsage
sudo certbot install --cert-name <ip-with-dashes>.sslip.io
```

The setup script installs Python 3.12 (via deadsnakes), ffmpeg, nginx, certbot, creates the venv, installs requirements, creates a systemd unit, and configures nginx as an SSE-friendly reverse proxy to `127.0.0.1:8000`.

### Frontend on Vercel

1. Import the repo on Vercel
2. **Root Directory**: `frontend`
3. **Env vars**:
   - `NEXT_PUBLIC_API_URL` = `https://<backend-domain>`
   - `NEXT_PUBLIC_API_KEY` = same as backend `API_KEY`
4. Deploy

Then lock `CORS_ORIGINS` on the backend to the Vercel URL and restart the service.

## Multi-Agent Pipeline Details

### Ingestion (SSE)
1. yt-dlp metadata - rejects live streams, premieres, and zero-duration content up front
2. Transcript: English captions -> translated captions -> Whisper on downloaded audio
3. Semantic chunking: merge captions into ~15s blocks, then split via `RecursiveCharacterTextSplitter` (1500 / 200)
4. GPT-4o structured summary (overview, detailed narrative, topics, takeaways, timeline) runs in parallel with chunking
5. Embed chunks and store in a per-video ChromaDB collection
6. Register the video in the SQLite `videos` table and create a chat session

### Planner (GPT-4o via OpenAI)
- RAG query on the collection for 15 overview chunks
- Asks GPT-4o for the top 3 concepts with titles, descriptions, timestamp ranges, and visual scene descriptions
- Attaches the relevant transcript segments to each concept

### Script writer (GPT-4o via OpenAI)
- For each concept, designs 2 infographic prompts (overview + deep dive)
- Both prompts are constrained to 9:16 vertical format with clean modern design language

### Video generator (Replicate Nano Banana Pro)
- 6 image generations in sequence (throttled through `asyncio.to_thread` so blocking Replicate polling never freezes the async event loop)
- Images downloaded, then ffmpeg concat demuxer stitches them at 5s per slide into a 1080x1920 H.264 MP4
- Path saved to the SQLite `videos` row so any future request can serve it without a running job

### Chat (SSE)
1. Load session + message history
2. Rewrite the user's conversational question into a standalone search query (GPT-4o, temp 0)
3. ChromaDB semantic search; filter by cosine distance < 1.0; keep top 3
4. Emit `sources` event so the frontend renders references before tokens arrive
5. Assemble: system prompt + video metadata + summary + rolling history summary + recent messages + question + transcript excerpts
6. Stream tokens via `ChatOpenAI.astream`, persist the final response

### Web search (SSE)
Alternative branch triggered by the "Web search" toggle. Uses `google-genai` with `Tool(google_search=GoogleSearch())` on `gemini-2.5-flash`. Streams Gemini's answer and collects grounding citations into a `web_sources` event.

## Security

- API key auth via `X-API-Key` header (or `?api_key=` query param for `<video src>`)
- CORS locked to the Vercel deployment
- HTTPS via Let's Encrypt on a free sslip.io subdomain
- Live streams / stations / premieres rejected before ingestion begins
- `replicate.run()` wrapped in `asyncio.to_thread` so blocking polls don't freeze the FastAPI event loop

## Cost per Full Run

| Component | Approx cost |
|---|---|
| GPT-4o summary | $0.01 |
| GPT-4o planner | $0.02 |
| GPT-4o script writer | $0.02 |
| GPT-4o chat (per message) | $0.01 |
| OpenAI embeddings | negligible |
| Gemini Flash (web search) | free tier |
| Nano Banana Pro (6 images) | ~$0.50 |
| **Total per infographic run** | **~$0.55** |

## Team

- Ronak Lakhotia (A0161401Y)
- Shivansh Srivastava (A0328697H)
