# YTSage — YouTube to Shorts Synthesis Agent

YTSage is a multi-agent AI system that transforms long-form YouTube lectures and tech talks into short-form educational infographic slideshows. Given a YouTube URL, it extracts the transcript, identifies key concepts, designs educational infographics, and stitches them into a video summary.

> This product is entirely derived from work conducted as part of the NUS CS5260 course.

## Architecture

```
User pastes YouTube URL
        |
        v
Transcript Extraction (YouTube Transcript API)
  - Extract transcript, merge into ~60s chunks
        |
        v
Planner Agent (GPT-4o via Replicate)
  - Identify top 3 concepts with timestamps
  - Attach relevant transcript segments to each concept
        |
        v
Script Writer Agent (GPT-4o via Replicate)
  - Design 2 infographic prompts per concept (overview + deep dive)
  - Grounded in actual transcript segments
        |
        v
Video Generator Agent (Nano Banana Pro via Replicate)
  - Generate 6 infographic images (2 per concept)
  - Stitch into a 30-second MP4 slideshow (ffmpeg)
        |
        v
Output — Infographic images + slideshow video
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI |
| Agent Orchestration | LangGraph (directed state graph) |
| LLM | GPT-4o via Replicate |
| Image Generation | Google Nano Banana Pro via Replicate |
| Transcript Extraction | youtube-transcript-api |
| Video Stitching | ffmpeg |
| Frontend | Next.js, TypeScript, Tailwind CSS |
| Caching | File-based (SHA256 by URL hash) |

### Multi-Agent Pipeline (LangGraph)

The system uses LangGraph to orchestrate 3 specialized agents in sequence with error-safe conditional routing:

```
planner --[ok]--> script_writer --[ok]--> video_generator --> END
    |                   |
    +--[error]-->END    +--[error]-->END
```

Each agent reads from and writes to a shared `YTSageState` (TypedDict), enabling structured data flow between stages.

## Project Structure

```
project/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI entry point + CORS
│   │   ├── config.py               # Settings (API keys, cost limits)
│   │   ├── models.py               # Pydantic models + LangGraph state
│   │   ├── routes/
│   │   │   └── api.py              # API endpoints (/process, /status, /result)
│   │   ├── agents/
│   │   │   ├── graph.py            # LangGraph state graph (planner → script_writer → video_generator)
│   │   │   ├── planner.py          # Concept ranking agent (GPT-4o)
│   │   │   ├── script_writer.py    # Infographic prompt designer (GPT-4o)
│   │   │   └── video_generator.py  # Image generation + slideshow (Nano Banana Pro + ffmpeg)
│   │   └── services/
│   │       ├── transcript.py       # YouTube transcript extraction + chunking
│   │       ├── cache.py            # File-based caching
│   │       └── infographic.py      # Pillow-based infographic fallback
│   ├── requirements.txt
│   ├── test_pipeline.py            # Step-by-step pipeline debugger
│   └── .env.example
├── frontend/
│   └── src/app/page.tsx            # Landing page (URL input)
├── Proposal.pdf                    # CS5260 project proposal
├── PLAN.md                         # Implementation plan + progress
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/process` | Submit a YouTube URL — kicks off the full pipeline |
| GET | `/api/status/{job_id}` | Poll job status and progress |
| GET | `/api/result/{job_id}` | Get completed results (infographics, slideshow) |
| POST | `/api/test-transcript` | Test transcript extraction for a URL |
| GET | `/health` | Health check |

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- ffmpeg (for video stitching)
- Replicate account with API token

### Backend Setup

**First time only:**

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your Replicate API token
```

**Run the server:**

```bash
./backend/run.sh
```

The backend runs at `http://localhost:8000`. Verify at `http://localhost:8000/health`.

**Test the pipeline step-by-step:**

```bash
cd backend
python test_pipeline.py 1    # Extract transcript
python test_pipeline.py 2    # Run planner (GPT-4o)
python test_pipeline.py 3    # Run script writer (GPT-4o)
python test_pipeline.py 4    # Generate infographics + slideshow
```

Each step saves its output to a JSON file. The next step loads from the previous step's output, so you can inspect and debug between steps.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:3000`.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `REPLICATE_API_TOKEN` | Replicate API token (for GPT-4o + Nano Banana Pro) | Yes |
| `MAX_COST_PER_SESSION_SGD` | Cost limit per session (default: 8.0) | No |
| `CACHE_DIR` | Directory for cached results (default: ./cache) | No |

## Agents

### Planner Agent
- **Model:** GPT-4o via Replicate
- **Input:** Merged transcript chunks
- **Output:** Top 3 concepts, each with title, description, timestamps, and relevant transcript segments
- **Cost:** ~$0.02 per call

### Script Writer Agent
- **Model:** GPT-4o via Replicate
- **Input:** Top 3 concepts with transcript segments
- **Output:** 2 infographic prompts per concept (overview + deep dive)
- **Cost:** ~$0.02 per call

### Video Generator Agent
- **Model:** Google Nano Banana Pro via Replicate
- **Input:** 6 infographic prompts from script writer
- **Output:** 6 infographic images + 1 stitched MP4 slideshow (30s, 5s per slide)
- **Cost:** ~$0.50 per run (6 images)

**Total estimated cost per video:** ~$0.55

## Course Relevance (CS5260)

This project incorporates concepts from multiple weeks of the CS5260 curriculum:

| Week | Topic | How it's used in YTSage |
|------|-------|------------------------|
| Week 1 | Transformers, MoE | Tested with 3Blue1Brown Attention video |
| Week 8 | Video Generation (DiT, Wan, Hunyuan) | Nano Banana Pro for infographic generation |
| Week 10 | LLM Agents (ReAct, AutoGen) | Multi-agent LangGraph pipeline |

## Cost Constraints

- Total API cost must stay under SGD 10 for testing
- Session aborts if estimated cost exceeds SGD 8
- All results cached by YouTube URL hash to avoid re-processing
- Estimated cost per run: ~$0.55

## Team

- Ronak Lakhotia (A0161401Y)
- Shivansh Srivastava (A0328697H)
