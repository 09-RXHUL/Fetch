import os
import re
import time
import uuid
import asyncio
import threading
import zipfile
import io
from typing import List
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
import requests
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC

app = FastAPI()
executor = ThreadPoolExecutor(max_workers=3)
active_jobs = {}
main_loop = None

# ---------- Global Log Capture ----------
class LogCapture:
    def __init__(self):
        self.messages = []
        self.subscribers = set()
        self.lock = threading.Lock()

    def log(self, message: str):
        with self.lock:
            self.messages.append(message)
            if len(self.messages) > 500:
                self.messages = self.messages[-500:]
        if main_loop:
            asyncio.run_coroutine_threadsafe(self.broadcast(message), main_loop)

    async def broadcast(self, message: str):
        for ws in list(self.subscribers):
            try:
                await ws.send_text(message)
            except:
                self.subscribers.discard(ws)

    def subscribe(self, ws: WebSocket):
        self.subscribers.add(ws)
        for msg in self.messages[-100:]:
            asyncio.run_coroutine_threadsafe(ws.send_text(msg), main_loop)

    def unsubscribe(self, ws: WebSocket):
        self.subscribers.discard(ws)

log_capture = LogCapture()

class YtDlpLogger:
    def __init__(self, capture: LogCapture):
        self.capture = capture
    def debug(self, msg): self.capture.log(f"[yt-dlp] {msg}")
    def info(self, msg): self.capture.log(f"[yt-dlp] {msg}")
    def warning(self, msg): self.capture.log(f"[yt-dlp] WARNING: {msg}")
    def error(self, msg): self.capture.log(f"[yt-dlp] ERROR: {msg}")

# ---------- Helpers ----------
def clean_filename(title):
    junk = [
        r'[\(\[\{]\s*(official\s*(music\s*)?video|lyric\s*video|lyrics|audio|4k|hd|visualizer|remastered)\s*[\)\]\}]',
        r'-\s*Topic$', r'\|.*$'
    ]
    clean = title
    for pat in junk:
        clean = re.sub(pat, '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'[\\/:*?"<>|]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean if clean else "Audio_Track"

def format_bytes(num):
    if not num or num <= 0:
        return "0 MB"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num < 1024.0:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} TB"

def fetch_metadata(url: str):
    ydl_opts = {"quiet": True, "skip_download": True, "logger": YtDlpLogger(log_capture)}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if "entries" in info:
            return [parse_track_info(entry) for entry in info["entries"]]
        else:
            return [parse_track_info(info)]

def parse_track_info(info):
    title = clean_filename(info.get("title", "Unknown"))
    duration = info.get("duration", 0)
    return {
        "id": info.get("id", str(uuid.uuid4())),
        "title": title,
        "artist": info.get("artist") or info.get("uploader", "Unknown Artist"),
        "album": info.get("album", "YouTube Single"),
        "url": info.get("webpage_url") or info.get("url"),
        "duration_str": time.strftime('%M:%S', time.gmtime(duration)) if duration else "N/A",
        "est_mp3": round(duration / 60 * 2.4, 1) if duration else 0,
        "est_wav": round(duration / 60 * 10.0, 1) if duration else 0,
        "thumbnail": info.get("thumbnail", "")
    }

# ---------- Pydantic models ----------
class SearchRequest(BaseModel):
    query: str
    limit: int = 5

class FetchRequest(BaseModel):
    url: str

class DownloadItem(BaseModel):
    url: str
    format: str
    title: str = ""

class DownloadRequest(BaseModel):
    items: List[DownloadItem]

class DownloadAllRequest(BaseModel):
    job_ids: List[str]

# ---------- Download progress hook ----------
def progress_hook(d, job_id):
    if job_id not in active_jobs:
        return
    if d["status"] == "downloading":
        active_jobs[job_id]["downloaded"] = d.get("downloaded_bytes", 0)
        active_jobs[job_id]["total"] = d.get("total_bytes", 0)
        active_jobs[job_id]["speed"] = d.get("speed", 0)
        if d.get("total_bytes"):
            percent = (d.get("downloaded_bytes", 0) / d["total_bytes"]) * 100
            log_capture.log(f"[download] {active_jobs[job_id]['title']} - {percent:.1f}% | {format_bytes(d.get('downloaded_bytes', 0))} | {format_bytes(d.get('speed', 0))}/s")
    elif d["status"] == "finished":
        active_jobs[job_id]["status"] = "processing"
        log_capture.log(f"[download] {active_jobs[job_id]['title']} - finished, processing...")

def download_audio(url: str, fmt: str, job_id: str, title: str):
    out_dir = "/tmp"
    os.makedirs(out_dir, exist_ok=True)
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, f"{job_id}.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            "preferredquality": "320" if fmt == "mp3" else "0",
        }],
        "progress_hooks": [lambda d: progress_hook(d, job_id)],
        "logger": YtDlpLogger(log_capture),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        track_title = clean_filename(info.get("title", title))
        final_path = os.path.join(out_dir, f"{job_id}.{fmt}")
        if not os.path.exists(final_path):
            for f in os.listdir(out_dir):
                if f.startswith(job_id):
                    os.rename(os.path.join(out_dir, f), final_path)
                    break
        return final_path, track_title

def embed_metadata(file_path, meta):
    try:
        audio = EasyID3(file_path)
        audio["title"] = meta["title"]
        audio["artist"] = meta["artist"]
        audio["album"] = meta["album"]
        audio.save()
        if meta.get("thumbnail"):
            img_data = requests.get(meta["thumbnail"]).content
            tags = ID3(file_path)
            tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=img_data))
            tags.save()
    except Exception as e:
        log_capture.log(f"[metadata] Could not embed: {e}")

def run_download_task(item: DownloadItem, job_id: str):
    try:
        log_capture.log(f"Starting download: {item.title or item.url} as {item.format}")
        file_path, title = download_audio(item.url, item.format, job_id, item.title)
        embed_metadata(file_path, {"title": title, "artist": "Unknown", "album": "", "thumbnail": ""})
        active_jobs[job_id]["status"] = "completed"
        active_jobs[job_id]["file_path"] = file_path
        active_jobs[job_id]["filename"] = f"{title}.{item.format}"
        active_jobs[job_id]["title"] = title
        log_capture.log(f"Download completed: {title}.{item.format}")
    except Exception as e:
        active_jobs[job_id]["status"] = "failed"
        active_jobs[job_id]["error"] = str(e)
        log_capture.log(f"Download failed: {str(e)}")

# ---------- Startup/Shutdown ----------
@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

@app.on_event("shutdown")
async def shutdown_event():
    executor.shutdown(wait=False)

# ---------- API endpoints ----------
@app.get("/", response_class=HTMLResponse)
async def index():
    with open("templates/index.html", "r") as f:
        return HTMLResponse(f.read())

@app.post("/search")
async def search(req: SearchRequest):
    log_capture.log(f"Searching YouTube: {req.query}")
    try:
        search_url = f"ytsearch{req.limit}:{req.query}"
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "logger": YtDlpLogger(log_capture)}) as ydl:
            info = ydl.extract_info(search_url, download=False)
            tracks = [parse_track_info(entry) for entry in info["entries"]]
        log_capture.log(f"Found {len(tracks)} results")
        return {"tracks": tracks}
    except Exception as e:
        log_capture.log(f"Search error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/fetch")
async def fetch(req: FetchRequest):
    log_capture.log(f"Fetching metadata for: {req.url}")
    try:
        tracks = fetch_metadata(req.url)
        log_capture.log(f"Fetched {len(tracks)} tracks")
        return {"tracks": tracks}
    except Exception as e:
        log_capture.log(f"Fetch error: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/download")
async def start_download(req: DownloadRequest):
    if not req.items:
        raise HTTPException(status_code=400, detail="No items selected")

    response = []
    for item in req.items:
        job_id = str(uuid.uuid4())
        active_jobs[job_id] = {
            "status": "downloading",
            "downloaded": 0,
            "total": 0,
            "speed": 0,
            "file_path": "",
            "filename": "",
            "title": item.title or item.url,
            "error": ""
        }
        response.append({"job_id": job_id, "title": item.title or item.url, "format": item.format})
        executor.submit(run_download_task, item, job_id)

    log_capture.log(f"Started {len(response)} download(s)")
    return {"jobs": response}

@app.get("/progress/{job_id}")
async def get_progress(job_id: str):
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = active_jobs[job_id]
    return {
        "job_id": job_id,
        "status": job["status"],
        "downloaded": job["downloaded"],
        "total": job["total"],
        "speed": job["speed"],
        "filename": job.get("filename", ""),
        "title": job.get("title", ""),
        "error": job.get("error", "")
    }

@app.get("/file/{job_id}")
async def get_file(job_id: str):
    job = active_jobs.get(job_id)
    if not job or job["status"] != "completed" or not job.get("file_path"):
        raise HTTPException(status_code=404, detail="File not ready")
    return FileResponse(job["file_path"], filename=job["filename"])

@app.post("/download_all")
async def download_all(req: DownloadAllRequest):
    # Collect files from completed jobs
    files_to_zip = []
    for jid in req.job_ids:
        job = active_jobs.get(jid)
        if job and job["status"] == "completed" and job.get("file_path"):
            files_to_zip.append((job["file_path"], job.get("filename", os.path.basename(job["file_path"]))))
    if not files_to_zip:
        raise HTTPException(status_code=404, detail="No completed files found")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path, arcname in files_to_zip:
            zf.write(file_path, arcname)
    zip_buffer.seek(0)
    return StreamingResponse(zip_buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=downloads.zip"})

@app.post("/update_ytdlp")
async def update_ytdlp():
    """Attempt to upgrade yt-dlp in the running environment (not persistent)."""
    log_capture.log("Updating yt-dlp via pip...")

    def run_update():
        try:
            import subprocess
            proc = subprocess.run(
                ["pip", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=120  # seconds
            )
            if proc.returncode == 0:
                log_capture.log("yt-dlp updated successfully. (Temporary – will not survive a restart.)")
            else:
                log_capture.log(f"pip update failed: {proc.stderr}")
        except Exception as e:
            log_capture.log(f"Update error: {e}")

    # Run in a separate thread to avoid blocking the event loop
    threading.Thread(target=run_update, daemon=True).start()

    return {"status": "started", "message": "Update started. Check terminal for progress."}

# WebSocket for logs
@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()
    log_capture.subscribe(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        log_capture.unsubscribe(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)