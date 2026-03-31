#!/usr/bin/env python3
"""
YouTube Downloader Backend
Powered by yt-dlp + ffmpeg
Serves both V1 (YTDL RIPPED) and V2 (Prism) frontends

Install dependencies:
    pip install yt-dlp

Optional (for post-processing):
    brew install ffmpeg        (macOS)
    sudo apt install ffmpeg    (Linux)
    winget install ffmpeg      (Windows)

Run:
    python ytdl_backend.py

Server listens on http://localhost:8080
"""

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask
from flask_cors import CORS

app = Flask(__name__)

# Tüm kökenlere (*) ve özel ngrok başlığına izin ver
CORS(app, resources={r"/*": {
    "origins": "*",
    "allow_headers": ["Content-Type", "ngrok-skip-browser-warning"]
}})

@app.route('/ping')
def ping():
    return {"status": "online"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "ngrok-skip-browser-warning"], # Buraya ekledik
)

try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    YT_DLP_AVAILABLE = False
    print("WARNING: yt-dlp not found. Run: pip install yt-dlp")

HOST = "localhost"
PORT = 8080
DOWNLOAD_DIR = str(Path.home() / "Downloads")

# ─────────────────────────────────────────────
# Helper: build yt-dlp options from request
# ─────────────────────────────────────────────
def build_ydl_opts(params: dict, progress_hook=None, output_dir: str = DOWNLOAD_DIR) -> dict:
    fmt       = params.get("format", "mp4").lower()
    quality   = params.get("quality", "best")
    aq        = params.get("audio_quality", "best")
    vcodec    = params.get("vcodec", "any")
    subtitles = params.get("subtitles", False)
    thumbnail = params.get("thumbnail", False)
    metadata  = params.get("metadata", False)
    playlist  = params.get("playlist", False)
    sb        = params.get("sponsorblock", False)
    chapters  = params.get("chapters", False)
    split     = params.get("split_chapters", False)
    out_tpl   = params.get("output", "")

    AUDIO_FORMATS = {"mp3", "m4a", "flac", "wav", "opus", "aac"}
    is_audio = fmt in AUDIO_FORMATS

    opts: dict = {
        "noplaylist": not playlist,
        "ignoreerrors": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,  # we use hooks instead
    }

    # ─── Format / codec selection ───
    if is_audio:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": fmt,
            **({"preferredquality": str(aq)} if aq != "best" else {}),
        }]
    else:
        if quality == "best":
            fmt_str = "bestvideo+bestaudio/best"
        else:
            fmt_str = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best[height<={quality}]"
        if vcodec != "any":
            fmt_str = fmt_str.replace("bestvideo", f"bestvideo[vcodec^={vcodec}]")
        opts["format"] = fmt_str
        opts["merge_output_format"] = fmt
        opts["postprocessors"] = []

    # ─── Post-processors ───
    pps = opts.setdefault("postprocessors", [])

    if subtitles:
        opts["writesubtitles"]  = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"]  = ["all"]
        opts["embedsubtitles"]  = True
        pps.append({"key": "FFmpegEmbedSubtitle"})

    if thumbnail:
        opts["writethumbnail"]  = True
        opts["embedthumbnail"]  = True
        pps.append({"key": "EmbedThumbnail"})

    if metadata:
        opts["addmetadata"] = True
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})

    if chapters:
        opts["addchapters"] = True
        pps.append({"key": "FFmpegMetadata", "add_chapters": True, "add_metadata": False})

    if split:
        pps.append({"key": "FFmpegSplitChapters", "force_keyframes": True})

    if sb:
        pps.append({"key": "SponsorBlock", "categories": ["sponsor"]})
        pps.append({"key": "ModifyChapters",
                    "remove_sponsor_segments": ["sponsor"],
                    "sponsorblock_chapter_title": "[SponsorBlock]: %(category_names)l"})

    # ─── Output template ───
    if out_tpl:
        opts["outtmpl"] = out_tpl
    else:
        opts["outtmpl"] = os.path.join(output_dir, "%(title)s.%(ext)s")

    # ─── Progress hook ───
    if progress_hook:
        opts["progress_hooks"] = [progress_hook]

    return opts


# ─────────────────────────────────────────────
# HTTP Request Handler
# ─────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # Simple console logging
        print(f"  [{self.command}] {self.path}  {args[1] if len(args) > 1 else ''}")

    def send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/ping":
            self._json({"status": "ok", "yt_dlp": YT_DLP_AVAILABLE})
        elif self.path == "/version":
            ver = yt_dlp.version.__version__ if YT_DLP_AVAILABLE else "not installed"
            self._json({"yt_dlp_version": ver})
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        raw     = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            self._json({"error": "Invalid JSON"}, 400)
            return

        if self.path == "/info":
            self._handle_info(body)
        elif self.path == "/download":
            self._handle_download(body)
        else:
            self._json({"error": "Not found"}, 404)

    # ── GET INFO ──────────────────────────────
    def _handle_info(self, body):
        if not YT_DLP_AVAILABLE:
            self._json({"error": "yt-dlp not installed"}, 503)
            return

        url = body.get("url", "").strip()
        if not url:
            self._json({"error": "No URL provided"}, 400)
            return

        try:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
                info = ydl.extract_info(url, download=False)

            # Return clean subset of metadata
            payload = {
                "title":          info.get("title"),
                "uploader":       info.get("uploader"),
                "description":    (info.get("description") or "")[:400],
                "duration":       info.get("duration"),
                "thumbnail":      info.get("thumbnail"),
                "view_count":     info.get("view_count"),
                "like_count":     info.get("like_count"),
                "upload_date":    info.get("upload_date"),
                "webpage_url":    info.get("webpage_url"),
                "width":          info.get("width"),
                "height":         info.get("height"),
                "fps":            info.get("fps"),
                "is_live":        info.get("is_live", False),
                "age_limit":      info.get("age_limit", 0),
                "playlist_count": info.get("playlist_count", 1),
                "categories":     info.get("categories", []),
                "tags":           (info.get("tags") or [])[:8],
                "formats":        [
                    {
                        "format_id": f.get("format_id"),
                        "ext":       f.get("ext"),
                        "height":    f.get("height"),
                        "width":     f.get("width"),
                        "fps":       f.get("fps"),
                        "vcodec":    f.get("vcodec"),
                        "acodec":    f.get("acodec"),
                        "filesize":  f.get("filesize"),
                        "tbr":       f.get("tbr"),
                        "abr":       f.get("abr"),
                    }
                    for f in (info.get("formats") or [])
                    if f.get("height") or f.get("acodec") != "none"
                ][-20:],  # last 20 best formats
            }
            self._json(payload)

        except yt_dlp.utils.DownloadError as e:
            self._json({"error": str(e)}, 400)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    # ── DOWNLOAD (streaming progress) ─────────
    def _handle_download(self, body):
        if not YT_DLP_AVAILABLE:
            self._send_event({"type": "error", "msg": "yt-dlp not installed"})
            return

        url = body.get("url", "").strip()
        if not url:
            self._send_event({"type": "error", "msg": "No URL provided"})
            return

        # Set up streaming response
        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

        result = {"filename": None, "filesize": None, "error": None}
        lock = threading.Lock()

        def progress_hook(d):
            status = d.get("status")
            if status == "downloading":
                pct      = d.get("_percent_str", "0%").strip().rstrip("%")
                speed    = d.get("_speed_str", "—").strip()
                eta      = d.get("_eta_str", "—").strip()
                total    = d.get("_total_bytes_str", d.get("_total_bytes_estimate_str", "—")).strip()
                frag     = "—"
                if d.get("fragment_index") is not None:
                    frag = f"{d.get('fragment_index')}/{d.get('fragment_count','?')}"
                try:
                    pct_f = float(pct)
                except Exception:
                    pct_f = 0.0
                ev = {
                    "type":     "progress",
                    "percent":  pct_f,
                    "speed":    speed,
                    "eta":      eta,
                    "size":     total,
                    "fragment": frag,
                }
                self._stream_event(ev)

            elif status == "finished":
                fn = d.get("filename") or d.get("info_dict", {}).get("filepath", "")
                sz = d.get("_total_bytes_str", "—").strip()
                with lock:
                    result["filename"] = fn
                    result["filesize"] = sz
                self._stream_event({"type": "log", "msg": f"Merging / post-processing…", "level": "info"})

        def postproc_hook(d):
            if d.get("status") == "started":
                pp_name = d.get("postprocessor", "")
                self._stream_event({"type": "log", "msg": f"Post-processor: {pp_name}", "level": "info"})
            elif d.get("status") == "finished":
                fn = d.get("info_dict", {}).get("filepath", "")
                if fn:
                    with lock:
                        result["filename"] = fn

        try:
            output_dir = body.get("output", "").strip()
            if not output_dir:
                output_dir = DOWNLOAD_DIR

            opts = build_ydl_opts(body, progress_hook=progress_hook, output_dir=output_dir)
            opts["postprocessor_hooks"] = [postproc_hook]

            self._stream_event({"type": "log", "msg": f"Starting download…", "level": "info"})
            self._stream_event({"type": "log", "msg": f"Format: {body.get('format','mp4').upper()}", "level": "info"})

            with yt_dlp.YoutubeDL(opts) as ydl:
                error_code = ydl.download([url])

            if error_code == 0 or result["filename"]:
                fn = result["filename"] or "file"
                sz = result["filesize"] or "—"
                self._stream_event({
                    "type": "done",
                    "filename": os.path.basename(str(fn)),
                    "filepath": str(fn),
                    "size": sz,
                })
            else:
                self._stream_event({"type": "error", "msg": "Download failed. Check URL or options."})

        except yt_dlp.utils.DownloadError as e:
            msg = str(e)
            # Strip noisy prefix
            msg = re.sub(r"^ERROR:\s*", "", msg)
            self._stream_event({"type": "error", "msg": msg})
        except BrokenPipeError:
            pass  # Client disconnected
        except Exception as e:
            self._stream_event({"type": "error", "msg": str(e)})

    # ── Helpers ───────────────────────────────
    def _json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _stream_event(self, data):
        try:
            line = (json.dumps(data) + "\n").encode()
            self.wfile.write(line)
            self.wfile.flush()
        except BrokenPipeError:
            pass

    def _send_event(self, data):
        """For non-streaming error responses."""
        body = (json.dumps(data) + "\n").encode()
        self.send_response(200)
        self.send_cors()
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────
def main():
    print("\n" + "═"*52)
    print("  YouTube Downloader Backend")
    print("  Powered by yt-dlp")
    print("═"*52)

    if not YT_DLP_AVAILABLE:
        print("\n  ✗ yt-dlp not found!\n  Install it with:  pip install yt-dlp\n")
    else:
        print(f"\n  ✓ yt-dlp {yt_dlp.version.__version__}")

    print(f"  ✓ Listening on  http://{HOST}:{PORT}")
    print(f"  ✓ Downloads →   {DOWNLOAD_DIR}")
    print(f"\n  Endpoints:")
    print(f"    GET  /ping      — health check")
    print(f"    GET  /version   — yt-dlp version")
    print(f"    POST /info      — fetch video metadata")
    print(f"    POST /download  — download (NDJSON stream)")
    print("\n  Open ytdl_v1_frontend.html or ytdl_v2_frontend.html in your browser.")
    print("  Press Ctrl+C to stop.\n")
    print("═"*52 + "\n")

    server = HTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
