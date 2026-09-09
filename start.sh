#!/bin/bash
# Upgrade yt-dlp to the latest version before starting
pip install --upgrade yt-dlp

# Start the FastAPI server
uvicorn main:app --host 0.0.0.0 --port 8000