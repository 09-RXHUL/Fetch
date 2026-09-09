Here is a **complete README.md** file for your project. It includes detailed setup, deployment, usage, and a dedicated **Known Issues** section to help you troubleshoot common problems.

```markdown
# Fetch – YouTube Audio Downloader (Web App)

A modern web application to search YouTube, fetch track metadata, and download audio as MP3 or WAV. Built with FastAPI, yt‑dlp, and a responsive Bootstrap frontend. Includes parallel downloads, live progress tracking, and an integrated process terminal.

## Features

- **Search YouTube** directly from the app.
- **Fetch** metadata from a single video URL or an entire playlist.
- **Select formats** per track (MP3 or WAV) with bulk select/collapse options.
- **Parallel downloads** – configurable number of concurrent downloads.
- **Live progress** – per‑track progress bars, speed, and size.
- **One‑click save all** – download all completed files as individual audio files.
- **Process terminal** – real‑time server and client logs via WebSocket.
- **Auto‑update** – `yt‑dlp` is upgraded on every container start (and can be triggered manually).
- **Responsive UI** – works on desktop and mobile browsers.

## Tech Stack

| Layer          | Technology                         |
|----------------|------------------------------------|
| Backend        | Python, FastAPI, uvicorn           |
| Download engine| yt‑dlp, FFmpeg                     |
| Metadata tags  | mutagen                            |
| Frontend       | HTML5, JavaScript, Bootstrap 5     |
| Deployment     | Docker (recommended) or manual     |

## Project Structure

```
Fetch/
├── main.py               # FastAPI backend (all API endpoints + download logic)
├── templates/
│   └── index.html        # Frontend (single page)
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container definition (includes FFmpeg)
├── start.sh              # Startup script (auto‑updates yt‑dlp, starts uvicorn)
└── README.md             # This file
```

## Requirements

- **Python 3.9+** (for local run)
- **FFmpeg** installed and available in PATH (or bundled in Docker)
- **Docker** (for containerised deployment)

## Installation (Local)

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/Fetch.git
   cd Fetch
   ```

2. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Ensure **FFmpeg** is installed and accessible from the command line.  
   - **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH.
   - **Linux**: `sudo apt install ffmpeg`
   - **macOS**: `brew install ffmpeg`

## Running Locally

Start the development server:

```bash
uvicorn main:app --reload
```

or

```bash
python -m uvicorn main:app --reload
```

Open your browser at `http://127.0.0.1:8000`.

> **Note**: The app will run with limited functionality if FFmpeg is missing – downloads will fail during post‑processing.

## Deployment (Render with Docker)

Render provides a free tier suitable for this app. The repository already includes a `Dockerfile` and `start.sh` for easy deployment.

1. Push this repository to GitHub.
2. Log in to [Render](https://render.com) and click **New + → Web Service**.
3. Connect your GitHub account and select the `Fetch` repository.
4. In the deployment settings:
   - **Environment**: `Docker`
   - **Build Command**: *(leave blank)*
   - **Start Command**: *(leave blank)*
   - **Health Check Path**: `/healthz` (the app includes this endpoint)
   - **Instance Type**: `Free`
5. Click **Create Web Service**.

Render will build the Docker image and deploy. The app will be available at a public URL like `https://fetch.onrender.com`.

### Automatic `yt‑dlp` Updates

The `start.sh` script runs `pip install --upgrade yt-dlp` every time the container starts. This ensures the engine is always up‑to‑date with the latest YouTube changes. The manual **Update Engine** button inside the app triggers the same command during runtime, but the update is temporary and lost on restart.

## Configuration

### Environment Variables

No environment variables are required. However, you can set the following if needed:

| Variable | Description                          | Default |
|----------|--------------------------------------|---------|
| `PORT`   | Port to listen on (set by Render)    | `8000`  |

### Adjusting Parallel Downloads

In `main.py`, the thread pool size is hardcoded:

```python
executor = ThreadPoolExecutor(max_workers=3)
```

Change `3` to any number to control how many downloads run concurrently. Keep in mind the free Render tier has limited CPU, so higher numbers may cause timeouts.

## API Endpoints

| Method | Endpoint                 | Description                              |
|--------|--------------------------|------------------------------------------|
| GET    | `/`                      | Serves the frontend                      |
| GET    | `/healthz`               | Health check                             |
| POST   | `/search`                | Search YouTube (body: `{query, limit}`)  |
| POST   | `/fetch`                 | Fetch metadata from URL/playlist         |
| POST   | `/download`              | Start downloads (body: `{items: [...]}`) |
| GET    | `/progress/{job_id}`     | Get progress of a single download        |
| GET    | `/file/{job_id}`         | Download completed audio file            |
| POST   | `/download_all`          | **(Optional)** Create ZIP of completed files (not used in current frontend) |
| POST   | `/update_ytdlp`          | Manually upgrade yt‑dlp                  |
| WS     | `/ws/logs`               | WebSocket for live log streaming         |

### Example `POST /search`

```json
{
  "query": "lofi hip hop",
  "limit": 5
}
```

### Example `POST /download`

```json
{
  "items": [
    {
      "url": "https://youtube.com/watch?v=...",
      "format": "mp3",
      "title": "Some Song"
    },
    {
      "url": "https://youtube.com/watch?v=...",
      "format": "wav",
      "title": "Another Song"
    }
  ]
}
```

## Usage

1. Enter a search query or paste a YouTube URL/playlist.
2. Click **Search** or **Fetch**.
3. Use the checkboxes to select MP3 or WAV for each track.
4. (Optional) Use the toolbar to clear, collapse unselected, or select all.
5. Click **Download Selected**.
6. Watch the progress bars and terminal for status.
7. When downloads complete, click individual **Download file** links or use **Download All Completed Files** to save all at once (browsers may ask for permission for multiple downloads).

## Troubleshooting

### Search returns 0 results on Render (but works locally)
YouTube often blocks datacenter IP addresses, including those used by Render’s free tier. This is a known limitation. Possible workarounds:
- Deploy to a platform with a residential IP (e.g., a home server with a VPN, or Oracle Cloud Free Tier which provides a dedicated IPv4).
- Use a proxy with `yt‑dlp` (not configured in this project).

### WebSocket errors / terminal not connecting
Ensure the backend is running and the WebSocket route `/ws/logs` is accessible. If behind a reverse proxy, WebSocket support must be enabled (Render handles this automatically).

### `start.sh` fails with `permission denied`
The Dockerfile includes `RUN chmod +x start.sh`, but sometimes line endings cause issues. Make sure `start.sh` uses Unix (LF) line endings. In VS Code, check the bottom‑right corner and change from `CRLF` to `LF`.

### Container crashes immediately
Check the Render logs for the exact error. Common causes:
- `start.sh` missing or not executable
- `uvicorn` not found (missing from `requirements.txt`)
- `main.py` has a syntax error or missing `app` variable
- Port mismatch (should use `$PORT`)

## Known Issues & Limitations

1. **YouTube IP Blocking on Render**:  
   The free Render instance uses shared datacenter IPs that YouTube frequently blocks for search and sometimes for downloads. This can result in `HTTP Error 403` or zero search results. The only reliable fix is to use a different hosting provider with a better IP reputation (e.g., Oracle Cloud Free Tier) or add proxy support to `yt-dlp`.

2. **Temporary File Storage**:  
   Files are saved in `/tmp` inside the container. They are lost when the container restarts or sleeps (free tier). Download links become invalid after that. For permanent storage, you would need to integrate cloud storage (S3, Google Drive, etc.).

3. **Multiple Download Limits**:  
   Browsers may block multiple automatic downloads triggered by “Download All”. The code adds a 1‑second delay between each file, but some browsers (like Chrome) still require user permission for multiple downloads. If blocked, users must click each file individually.

4. **WebSocket Reconnection Loop**:  
   In some cases, the WebSocket may fail to connect due to proxy or network issues. The frontend will attempt to reconnect every 3 seconds. If the server is restarting, this is normal; otherwise, check the server logs for WebSocket errors.

5. **Free Tier Resource Limits**:  
   Render’s free tier has limited CPU and memory. Concurrent downloads (more than 2–3) may cause timeouts or crashes. Adjust `ThreadPoolExecutor(max_workers=...)` to a lower number if you experience instability.

6. **Auto‑update Not Persistent**:  
   The `Update Engine` button upgrades `yt-dlp` only in the running container. After a restart, the old version from the Docker image is restored. The `start.sh` script solves this by updating on every startup, but there is a short delay while `pip` runs.

7. **Playlists with Many Items**:  
   Fetching very large playlists (hundreds of videos) can take a long time and may hit memory limits. The app currently fetches all entries at once. For large playlists, consider adding pagination or increasing the container size.

## Legal Disclaimer

This tool is intended for downloading audio from YouTube for personal use only. Users are responsible for ensuring they have the right to download the content. Downloading copyrighted material without permission may violate YouTube’s Terms of Service and applicable laws.

## License

This project is provided as-is without any warranty. Feel free to modify and use it for personal projects.

---

**Made with ❤️ using Python and FastAPI.**
```

---
