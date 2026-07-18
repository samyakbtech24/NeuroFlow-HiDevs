#!/bin/bash

# Start the Celery/Redis background worker in the background
python -m worker &

# Start the FastAPI Web Server in the foreground
uvicorn backend.api.main:app --host 0.0.0.0 --port $PORT
