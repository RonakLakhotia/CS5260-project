# YTSage — Conversational YouTube Assistant with Multi-Agent Infographic Synthesis

**NUS CS5260 — Final Project Report**

| | |
|---|---|
| **Team** | Ronak Lakhotia (A0161401Y) · Shivansh Srivastava (A0328697H) |
| **Project option** | Option 1 — Build a live, publicly accessible AI agent |
| **Frontend** | https://cs-5260-project.vercel.app |
| **Backend API** | https://168-144-130-174.sslip.io |
| **Source** | https://github.com/RonakLakhotia/CS5260-project |

---

## 1. Abstract

YTSage is a multi-agent AI system that turns any YouTube video into a conversational assistant. A user pastes a YouTube URL and, in parallel, three things happen: the transcript is ingested into a per-video vector store, a LangGraph pipeline generates a 30-second educational infographic slideshow, and a streaming chat session becomes available. The chat answers grounded questions against the transcript (RAG with GPT-4o) or falls back to the live web via Gemini with Google-Search grounding — the choice is made automatically by an LLM router per question, with a manual override toggle for users who explicitly want web answers. The entire product is deployed publicly: the FastAPI backend on a Digital Ocean droplet with HTTPS and API-key auth, and the Next.js frontend on Vercel.

## 2. Features

### 2.1 Chat with the video
- Token-by-token streaming responses over Server-Sent Events.
- RAG against transcript chunks stored in a per-video ChromaDB collection; results filtered by cosine distance.
- Conversational follow-ups ("explain that further") are rewritten into standalone search queries before retrieval, using the last 4 turns of context.
- Conversation history persisted in SQLite with a rolling summary for long sessions.
- Up to 3 transcript "Video references" shown under each answer — each has a **Play** button that seeks the embedded YouTube player in place via the iframe API (no tab switches, no state loss).

### 2.2 Auto-routed web search (with manual override)
Every chat question is routed automatically:
- **Default behavior:** an LLM router (`gpt-4o-mini`, temperature 0, ~3-token output) classifies the question as `transcript` or `web` using the video title, description, and recent conversation as context. Ambiguous questions default to `transcript` because users are here to chat with the video.
- **Manual override:** a "Web search" toggle in the chat input bar forces the web path regardless of router output, for cases where the user explicitly wants external information.
- **Web path:** Gemini 2.5 Flash with the `google_search` tool. Streams the answer and emits grounding citations as "Web sources".

Examples that route automatically:
| Question | Route |
|---|---|
| "Summarize the video" | `transcript` |
| "What did he say about AI safety?" | `transcript` |
| "What's the weather in Singapore right now?" | `web` |
| "Who won the 2025 ICC Champions Trophy?" | `web` |

### 2.3 Infographic slideshow
- Runs concurrently with the chat; the user is never blocked.
- A subtle pill above the chat input shows live pipeline progress (expandable to see each step, with check marks for completed stages).
- Transitions to a green "Slideshow ready" pill when the MP4 is available; clicking opens a floating video player.
- State survives page refreshes — looked up per-video from SQLite, so any browser/device sees the correct status.

### 2.4 Storage
All three storage systems are linked by `video_id`:
- `yt_{video_id}` ChromaDB collection → transcript chunks + embeddings
- `videos` SQLite table → metadata, slideshow path, pipeline job id
- `./cache/videos/slideshow_{video_id}.mp4` → stitched video file

## 3. Architecture

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


[Chat SSE]
   question
     |
     v
   [Router: gpt-4o-mini]---transcript---> RAG + GPT-4o
     |                                       |
     | web (or toggle forces web)            v
     v                              streaming answer
   Gemini 2.5 Flash + Google Search
     |
     v
   streaming answer + citations
```

The chat, ingestion, and infographic pipeline all run in parallel — a user can chat with the transcript while the slideshow is still being generated.

## 4. Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Agent orchestration | LangGraph |
| LLM (pipeline + chat) | OpenAI GPT-4o |
| LLM (router) | OpenAI GPT-4o-mini (classification only) |
| LLM (web search) | Gemini 2.5 Flash with Google Search grounding |
| Image generation | Google Nano Banana Pro (via Replicate) |
| Video stitching | ffmpeg |
| Transcript | youtube-transcript-api + OpenAI Whisper fallback (yt-dlp for audio) |
| Vector store | ChromaDB (cosine distance) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Chat persistence | SQLite (aiosqlite, WAL mode) |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind 4 |
| Markdown rendering | react-markdown |
| Deployment (backend) | Digital Ocean droplet (Ubuntu 24.04) + nginx + Let's Encrypt (sslip.io) + systemd |
| Deployment (frontend) | Vercel |

## 5. Multi-Agent Pipeline Details

### 5.1 Ingestion (SSE)
1. **yt-dlp metadata** — rejects live streams, premieres, and zero-duration content up front.
2. **Transcript** — tries English captions → translated captions → OpenAI Whisper on downloaded audio.
3. **Semantic chunking** — merge captions into ~15s blocks, then split via `RecursiveCharacterTextSplitter` (1500 / 200).
4. **GPT-4o structured summary** (overview, detailed narrative, topics, takeaways, timeline) runs in parallel with chunking.
5. **Embed** chunks and store in a per-video ChromaDB collection.
6. **Register** the video in the SQLite `videos` table and create a chat session.

### 5.2 Planner (GPT-4o)
- RAG query on the collection for 15 overview chunks.
- Asks GPT-4o for the top 3 concepts with titles, descriptions, timestamp ranges, and visual scene descriptions.
- Attaches the relevant transcript segments to each concept.

### 5.3 Script writer (GPT-4o)
- For each concept, designs 2 infographic prompts (overview + deep dive).
- Both prompts are constrained to 9:16 vertical format with a clean modern design language.

### 5.4 Video generator (Replicate Nano Banana Pro)
- 6 image generations in sequence (throttled through `asyncio.to_thread` so blocking Replicate polling never freezes the async event loop).
- Images downloaded, then ffmpeg concat demuxer stitches them at 5s per slide into a 1080×1920 H.264 MP4.
- Path saved to the SQLite `videos` row so any future request can serve it without a running job.

### 5.5 Chat router (GPT-4o-mini)
- Short classification prompt (`transcript` vs `web`), temperature 0, `max_tokens=3`.
- Receives video title, video description, and the last 2 conversation turns as context.
- Defaults to `transcript` on errors or ambiguity.
- Logs every decision (`Route=transcript q=...`) for evaluation.

### 5.6 Chat — transcript path (SSE)
1. Load session + message history.
2. Rewrite the user's conversational question into a standalone search query (GPT-4o, temp 0).
3. ChromaDB semantic search; filter by cosine distance < 1.0; keep top 3.
4. Emit `sources` event so the frontend renders references before tokens arrive.
5. Assemble: system prompt + video metadata + summary + rolling history summary + recent messages + question + transcript excerpts.
6. Stream tokens via `ChatOpenAI.astream`, persist the final response.

### 5.7 Chat — web path (SSE)
- Uses `google-genai` with `Tool(google_search=GoogleSearch())` on `gemini-2.5-flash`.
- Streams Gemini's answer and collects grounding citations into a `web_sources` event.

## 6. API

All `/api/*` endpoints require an `X-API-Key` header (or `?api_key=` query param for media URLs).

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ingest` | SSE stream: metadata → transcript → summary → embedding → done |
| GET | `/api/ingest/{video_id}` | Polling fallback for ingestion status |
| POST | `/api/process` | Kick off the LangGraph infographic pipeline |
| GET | `/api/status/{job_id}` | Poll pipeline status |
| GET | `/api/result/{job_id}` | Completed pipeline result |
| GET | `/api/slideshow/video/{video_id}` | Serve slideshow MP4 (survives backend restarts via SQLite lookup) |
| GET | `/api/videos` | List all ingested videos |
| GET | `/api/videos/{video_id}` | Get a video's metadata + slideshow/pipeline status |
| POST | `/api/chat/sessions` | Create a chat session |
| POST | `/api/chat/sessions/{chat_id}/messages` | SSE stream: status → sources → tokens → done |
| GET | `/api/chat/sessions/{chat_id}/messages` | Full message history |
| GET | `/health` | Health check (no auth) |

SSE events the frontend consumes:
- `status` — `searching_transcript`, `reviewing_history`, `searching_web`, `generating`
- `sources` — top 3 transcript chunks with timestamps
- `web_sources` — Gemini grounding citations
- `token` — streaming text chunk
- `done` — final `message_id`
- `error` — failure message

## 7. Project Structure

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
      chat_sessions.py          # Session chat + router + web search branch
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
      router.py                 # GPT-4o-mini classifier (transcript vs web)
      sse.py                    # SSE helpers
      formatting.py, cache.py, infographic.py
  run.sh, run-prod.sh
  requirements.txt
  .env.example
frontend/
  src/
    app/
      page.tsx                  # Home — URL input with SSE ingestion progress
      chat/[chatId]/page.tsx    # Main chat UI (video + messages + references + slideshow banner)
      processing/[jobId]/page.tsx
      results/[jobId]/page.tsx
      layout.tsx, globals.css
    lib/api.ts                  # apiFetch + withApiKey helpers
deploy/
  setup-gce.sh                  # One-shot VM bootstrap (python 3.12, ffmpeg, nginx, systemd) — platform-agnostic, used for DO
```

## 8. Local Development

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
| `OPENAI_API_KEY` | OpenAI API key (embeddings, GPT-4o for chat/planner/script writer/summary, GPT-4o-mini for the router, Whisper) |
| `REPLICATE_API_TOKEN` | Replicate token (Nano Banana Pro image generation only) |
| `GEMINI_API_KEY` | Google AI Studio API key (web search with Google grounding) |
| `API_KEY` | If set, all `/api/*` endpoints require `X-API-Key` header or `?api_key=` query param |
| `CORS_ORIGINS` | Comma-separated list of allowed origins. Default `*` |
| `CHROMA_PERSIST_DIR` | ChromaDB path, default `./chroma_db` |
| `CHAT_DB_PATH` | SQLite path, default `./chat.db` |
| `CACHE_DIR` | Video cache path, default `./cache` |
| `LLM_MODEL` | Default `gpt-4o` (used for chat + pipeline, not the router) |
| `EMBEDDING_MODEL` | Default `text-embedding-3-small` |

**frontend/.env.local**

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_URL` | Backend base URL, e.g. `https://168-144-130-174.sslip.io` |
| `NEXT_PUBLIC_API_KEY` | Must match backend `API_KEY` |

## 9. Deployment

### 9.1 Production setup (as deployed)

- **Backend:** Digital Ocean droplet — Ubuntu 24.04, 2 vCPU / 2 GB RAM / 60 GB SSD, Singapore region (`SGP1`), 2 GB swap file for safety during install and burst load.
- **Frontend:** Vercel, with `NEXT_PUBLIC_API_URL` pointed at the DO backend and `NEXT_PUBLIC_API_KEY` matching the backend's `API_KEY`.
- **Domain:** free `sslip.io` subdomain (`168-144-130-174.sslip.io`) — resolves automatically to the droplet IP.
- **TLS:** Let's Encrypt via certbot, auto-renews via cron.

### 9.2 Backend bootstrap

Full VM bootstrap is automated by [`deploy/setup-gce.sh`](deploy/setup-gce.sh) (the script is platform-agnostic Ubuntu bootstrap — it was originally written for GCE but is used for Digital Ocean without modification):

```bash
# 1. Create a Digital Ocean droplet (Ubuntu 24.04, Basic → 2 vCPU/2 GB/60 GB, SGP1, add SSH key)
# 2. SSH in as root and add a 2 GB swap file
ssh root@<droplet-ip>
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile \
    && echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 3. Clone the repo and run the bootstrap script
apt-get update && apt-get install -y git
git clone https://github.com/RonakLakhotia/CS5260-project.git /opt/ytsage
bash /opt/ytsage/deploy/setup-gce.sh

# 4. Populate /opt/ytsage/backend/.env with real keys + CORS + API_KEY
nano /opt/ytsage/backend/.env
sudo systemctl restart ytsage

# 5. HTTPS via sslip.io — free wildcard DNS that resolves to any IP
sudo certbot --nginx -d <ip-with-dashes>.sslip.io --non-interactive --agree-tos -m <email> --redirect
sudo sed -i "s/server_name _;/server_name <ip-with-dashes>.sslip.io;/" /etc/nginx/sites-available/ytsage
sudo systemctl reload nginx
sudo certbot install --cert-name <ip-with-dashes>.sslip.io
```

The setup script installs Python 3.12, ffmpeg, nginx, certbot; creates the venv; installs requirements; creates a systemd unit (`ytsage.service`); and configures nginx as an SSE-friendly reverse proxy to `127.0.0.1:8000`.

Useful droplet commands:
- `sudo systemctl status ytsage` — check status
- `sudo journalctl -u ytsage -f` — live logs (includes router decisions)
- `sudo systemctl restart ytsage` — restart after `.env` changes

### 9.3 Frontend deployment

1. Import the repo on Vercel.
2. **Root Directory:** `frontend`.
3. **Environment variables:**
   - `NEXT_PUBLIC_API_URL` = `https://168-144-130-174.sslip.io`
   - `NEXT_PUBLIC_API_KEY` = same value as the backend `API_KEY`
4. Deploy.

Then lock `CORS_ORIGINS` on the backend to the Vercel URL and restart the service.

## 10. Security

- **Auth:** API-key middleware requires `X-API-Key` on all `/api/*`. A query-param form (`?api_key=`) is accepted on media URLs (`<video src>`) where custom headers cannot be set.
- **CORS:** locked to the Vercel frontend origin in production.
- **TLS:** HTTPS via Let's Encrypt on a sslip.io subdomain, auto-renewing.
- **Input validation:** live streams, premieres, and zero-duration videos are rejected before ingestion begins.
- **Async safety:** `replicate.run()` wrapped in `asyncio.to_thread` so blocking polls do not freeze the FastAPI event loop.

## 11. Cost per Full Run

| Component | Approx cost |
|---|---|
| GPT-4o summary | $0.01 |
| GPT-4o planner | $0.02 |
| GPT-4o script writer | $0.02 |
| GPT-4o-mini router | ≈ $0.00003 per chat message |
| GPT-4o chat (per message) | $0.01 |
| OpenAI embeddings | negligible |
| Gemini Flash (web search) | free tier |
| Nano Banana Pro (6 images) | ~$0.50 |
| **Total per infographic run** | **~$0.55** |

The full end-to-end cost (ingest + slideshow + ~10 chat messages) stays well below the SGD 10 test budget per the project brief.

## 12. Team

- Ronak Lakhotia (A0161401Y)
- Shivansh Srivastava (A0328697H)
