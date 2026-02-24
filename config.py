import os
import uuid
import asyncio
import yt_dlp
import time
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(title="Cursed YT API")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

TOKENS = {}
TOKEN_EXPIRE_MINUTES = 10

# 🚀 Increased workers for speed
executor = ThreadPoolExecutor(max_workers=8)

# 🔥 Stats
START_TIME = time.time()
TOTAL_REQUESTS = 0


# ---------------- TOKEN SYSTEM ---------------- #

def generate_token(video_id):
    token = str(uuid.uuid4())
    expiry = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    TOKENS[video_id] = {"token": token, "expiry": expiry}
    return token


def validate_token(video_id, token):
    data = TOKENS.get(video_id)
    if not data:
        return False
    if data["token"] != token:
        return False
    if datetime.utcnow() > data["expiry"]:
        del TOKENS[video_id]
        return False
    return True


async def cleanup_tokens():
    while True:
        now = datetime.utcnow()
        expired = [k for k, v in TOKENS.items() if now > v["expiry"]]
        for k in expired:
            del TOKENS[k]
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_tokens())


# ---------------- ROOT PAGE ---------------- #

@app.get("/")
async def root():
    uptime = int(time.time() - START_TIME)
    hours = uptime // 3600
    minutes = (uptime % 3600) // 60

    return {
        "status": "online",
        "developer": "@JinWoonHwi",
        "uptime_hours": hours,
        "uptime_minutes": minutes,
        "total_requests": TOTAL_REQUESTS,
        "message": "Cursed YouTube API Running 🚀"
    }


# ---------------- YT-DLP CORE ---------------- #

def download_with_ytdlp(video_url, file_path, format_type):
    ydl_opts = {
        "format": format_type,
        "outtmpl": file_path,
        "quiet": True,
        "nocheckcertificate": True,
        "noplaylist": True,
        "geo_bypass": True,
        "retries": 10,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 5,
        "http_headers": {
            "User-Agent": "Mozilla/5.0"
        },
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])


# ---------------- DOWNLOAD ---------------- #

@app.get("/download")
async def download(url: str, type: str = "audio"):
    global TOTAL_REQUESTS
    TOTAL_REQUESTS += 1

    if not url:
        raise HTTPException(status_code=400, detail="No URL")

    video_url = f"https://www.youtube.com/watch?v={url}"

    if type == "audio":
        filename = f"{url}.mp3"
        format_type = "bestaudio/best"
    else:
        filename = f"{url}.mp4"
        format_type = "bestvideo+bestaudio/best"

    file_path = os.path.join(DOWNLOAD_DIR, filename)

    if not os.path.exists(file_path):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            executor,
            download_with_ytdlp,
            video_url,
            file_path,
            format_type
        )

    token = generate_token(url)
    return {"download_token": token}


# ---------------- STREAM ---------------- #

@app.get("/stream/{video_id}")
async def stream(
    video_id: str,
    type: str = "audio",
    x_download_token: Optional[str] = Header(None)
):
    global TOTAL_REQUESTS
    TOTAL_REQUESTS += 1

    if not x_download_token:
        raise HTTPException(status_code=403, detail="Token missing")

    if not validate_token(video_id, x_download_token):
        raise HTTPException(status_code=403, detail="Invalid token")

    filename = f"{video_id}.mp3" if type == "audio" else f"{video_id}.mp4"
    file_path = os.path.join(DOWNLOAD_DIR, filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path)


# ---------------- SEARCH ---------------- #

@app.get("/search")
async def search(query: str):
    global TOTAL_REQUESTS
    TOTAL_REQUESTS += 1

    if not query:
        raise HTTPException(status_code=400, detail="No query")

    try:
        search_query = f"ytsearch5:{query}"

        ydl_opts = {
            "quiet": True,
            "skip_download": True,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "web"]
                }
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)

        results = []
        for entry in info.get("entries", []):
            results.append({
                "title": entry.get("title"),
                "id": entry.get("id"),
                "duration": entry.get("duration"),
                "thumbnail": entry.get("thumbnail"),
                "uploader": entry.get("uploader"),
                "views": entry.get("view_count"),
            })

        return {"results": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
