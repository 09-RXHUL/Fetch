#!/bin/bash
# Upgrade yt-dlp to the latest version
pip install --upgrade yt-dlp

# Start the server on Render's expected port
exec uvicorn main:app --host 0.0.0.0 --port $PORT