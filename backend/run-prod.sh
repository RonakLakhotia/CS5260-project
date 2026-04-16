#!/bin/bash
# Production server - no reload, 0.0.0.0 binding, multiple workers
cd "$(dirname "$0")"
source venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
