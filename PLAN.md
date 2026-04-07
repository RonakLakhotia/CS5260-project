# YTSage — Current Plan & Next Steps

**Last updated:** 2026-03-31

## Completed

- [x] **Step 1 — Scaffolding**
  - Git repo initialized, `.gitignore` created
  - Backend: FastAPI skeleton with routes, models, config, services, agent stubs
  - Frontend: Next.js app with landing page (URL input + NUS CS5260 attribution)
  - `run.sh` script for easy backend startup
  - README with setup instructions, roadmap, and API docs

- [x] **Step 2 (partial) — Transcript Extraction**
  - `backend/app/services/transcript.py` — `get_transcript()` and `merge_chunks()` implemented
  - `/api/test-transcript` endpoint added for testing
  - Dependencies installed (`youtube-transcript-api` v0.6.3)
  - **NOT YET TESTED** with a real YouTube URL — need to run server and hit the curl endpoint

## Next Steps (in order)

### 1. Test transcript extraction
- Run `./backend/run.sh`
- Hit `/api/test-transcript` with a real YouTube URL
- Verify raw chunks and merged chunks look correct
- Fix any issues

### 2. Planner Agent
- File: `backend/app/agents/planner.py`
- Wire up GPT-4o via `langchain-openai`
- Input: merged transcript chunks
- Output: top 3 concepts ranked by importance, each with title, relevant segments, timestamps, justification
- Needs `OPENAI_API_KEY` in `.env`

### 3. Script Writer Agent
- File: `backend/app/agents/script_writer.py`
- Wire up GPT-4o
- Input: top 2 concepts + their transcript segments
- Output: ~30-sec narration script per concept (~75-90 words), grounded in transcript

### 4. Citation Mapper
- File: `backend/app/agents/citation_mapper.py`
- Wire up GPT-4o
- Input: scripts + transcript segments
- Output: each claim mapped to a YouTube timestamp URL (`?t=` parameter)

### 5. Wire LangGraph pipeline end-to-end
- File: `backend/app/agents/graph.py` (already has skeleton)
- Connect agents into state graph
- Make `/api/process` run the graph async in background
- Update job status at each step for `/api/status` polling
- Store results for `/api/result`

### 6. Frontend — Results + Processing pages
- Results page: 2 concept cards with scripts + clickable citation links
- Processing page: progress indicator polling `/api/status`
- Navigation: landing → processing → results

### 7. Video Generation (Week 2)
- Integrate Runway or Kling API
- Add video generation node to LangGraph graph
- Cost check before calling API
- Embed videos in results page

### 8. Deploy + Polish (Week 3)
- Deploy backend to Railway/Render
- Deploy frontend to Vercel
- Error handling, edge cases
- UI polish
- Pre-generate demo examples
- Prepare 5-min presentation

## Key Files

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI entry point |
| `backend/app/routes/api.py` | All API endpoints |
| `backend/app/agents/graph.py` | LangGraph state graph |
| `backend/app/agents/planner.py` | Concept ranking agent |
| `backend/app/agents/script_writer.py` | Script writing agent |
| `backend/app/agents/citation_mapper.py` | Citation mapping agent |
| `backend/app/agents/video_generator.py` | Video generation agent |
| `backend/app/services/transcript.py` | YouTube transcript extraction |
| `backend/app/services/cache.py` | Caching layer |
| `backend/app/models.py` | State schema + API models |
| `frontend/src/app/page.tsx` | Landing page |

## Constraints to Remember

- Total API cost must stay under SGD 10
- Abort if session cost > SGD 8
- Max 2 auto-generated videos, 3rd is on-demand only
- Cache results by URL hash
- Deadline: 2026-04-17 (presentation on Zoom)
