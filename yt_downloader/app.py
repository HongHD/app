import os
import re
import uuid
import shutil
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, abort
import yt_dlp

app = Flask(__name__)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 진행 상태 저장
progress_store: dict[str, dict] = {}

# ── 영상 정보 캐시 (URL → info dict)  ──────────────────────────────────
info_cache: dict[str, dict] = {}


# ── URL 검증 ───────────────────────────────────────────────────────────
YT_PATTERNS = [
    re.compile(r"^https?://(www\.)?youtube\.com/watch\?.*v=[\w-]+"),
    re.compile(r"^https?://youtu\.be/[\w-]+"),
    re.compile(r"^https?://(www\.)?youtube\.com/shorts/[\w-]+"),
    re.compile(r"^https?://music\.youtube\.com/watch\?.*v=[\w-]+"),
]

def is_valid_youtube_url(url: str) -> bool:
    return any(p.match(url.strip()) for p in YT_PATTERNS)


# ── 공통 yt-dlp 기본 옵션 ──────────────────────────────────────────────
BASE_OPTS = {
    "nocheckcertificate": True,
    "quiet": True,
    "no_warnings": True,
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    },
    # 동시 조각 다운로드 (속도 향상 핵심)
    "concurrent_fragment_downloads": 4,
    # 재시도 줄이기 (빠른 실패)
    "retries": 2,
    "fragment_retries": 2,
    # 소켓 타임아웃
    "socket_timeout": 10,
    # 불필요한 플레이리스트 처리 방지
    "noplaylist": True,
}


# ── 진행률 훅 ──────────────────────────────────────────────────────────
def make_progress_hook(task_id: str):
    def hook(d):
        s = d.get("status", "")
        if s == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            pct = int(downloaded / total * 100) if total > 0 else 0
            progress_store[task_id].update({
                "status": "downloading",
                "percent": pct,
                "speed": d.get("_speed_str", "").strip(),
                "eta":   d.get("_eta_str",   "").strip(),
            })
        elif s == "finished":
            progress_store[task_id].update({
                "status": "processing",
                "percent": 100,
                "speed": "",
                "eta": "",
            })
        elif s == "error":
            progress_store[task_id].update({
                "status": "error",
                "message": str(d.get("error", "오류 발생")),
            })
    return hook


# ── 다운로드 스레드 ────────────────────────────────────────────────────
def download_task(task_id: str, url: str, fmt: str, quality: str):
    out_path = DOWNLOAD_DIR / task_id
    out_path.mkdir(exist_ok=True)

    progress_store[task_id] = {
        "status": "starting", "percent": 0,
        "speed": "", "eta": "", "filename": "", "filepath": "", "message": "",
    }

    try:
        opts = {
            **BASE_OPTS,
            "outtmpl": str(out_path / "%(title).100s.%(ext)s"),
            "progress_hooks": [make_progress_hook(task_id)],
        }

        if fmt == "mp3":
            # ── MP3: 오디오만 다운 → 변환 ──────────────────────────
            quality_map = {"best": "0", "high": "2", "medium": "5", "low": "7"}
            aq = quality_map.get(quality, "2")
            opts.update({
                # bestaudio[ext=webm] 우선: 보통 단일 파일이라 merge 불필요
                "format": "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": aq,
                }],
                # 썸네일 임베드 제거 → 변환 시간 단축
                "writethumbnail": False,
            })

        else:  # mp4
            # ── MP4: 화질별 포맷 선택 ───────────────────────────────
            # 가능하면 이미 합쳐진 mp4를 우선 선택 → merge 불필요 → 빠름
            q_map = {
                "best":  ("bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                          "/bestvideo[ext=mp4]+bestaudio"
                          "/best[ext=mp4]/best"),
                "1080p": ("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                          "/bestvideo[height<=1080]+bestaudio"
                          "/best[height<=1080][ext=mp4]/best[height<=1080]"),
                "720p":  ("bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]"
                          "/bestvideo[height<=720]+bestaudio"
                          "/best[height<=720][ext=mp4]/best[height<=720]"),
                "480p":  ("bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]"
                          "/best[height<=480][ext=mp4]/best[height<=480]"),
                "360p":  ("bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]"
                          "/best[height<=360][ext=mp4]/best[height<=360]"),
            }
            opts.update({
                "format": q_map.get(quality, q_map["best"]),
                "merge_output_format": "mp4",
                # ffmpeg 코덱 복사 (재인코딩 없음) → 변환 수십 배 빠름
                "postprocessor_args": {
                    "ffmpeg": ["-c:v", "copy", "-c:a", "copy"]
                },
                "postprocessors": [{"key": "FFmpegMetadata"}],
            })

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        # 완료 파일 탐색
        ext = "mp3" if fmt == "mp3" else "mp4"
        files = sorted(out_path.glob(f"*.{ext}"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not files:
            files = sorted(out_path.glob("*.*"), key=lambda f: f.stat().st_mtime, reverse=True)

        if files:
            fp = files[0]
            progress_store[task_id].update({
                "status": "done", "percent": 100,
                "filename": fp.name,
                "filepath": str(fp),
                "title": (info or {}).get("title", fp.stem),
            })
        else:
            raise FileNotFoundError("완료된 파일을 찾을 수 없습니다.")

    except yt_dlp.utils.DownloadError as e:
        msg = str(e).lower()
        if "age" in msg or "sign in" in msg:
            friendly = "연령 제한 영상입니다."
        elif "private" in msg:
            friendly = "비공개 영상입니다."
        elif "unavailable" in msg or "removed" in msg:
            friendly = "삭제되었거나 이용 불가한 영상입니다."
        elif "copyright" in msg:
            friendly = "저작권 제한으로 다운로드할 수 없습니다."
        else:
            friendly = f"다운로드 오류: {str(e)[:180]}"
        progress_store[task_id].update({"status": "error", "message": friendly})

    except Exception as e:
        progress_store[task_id].update({"status": "error", "message": str(e)[:200]})


# ── 라우트 ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/info", methods=["POST"])
def get_info():
    """영상 정보 조회 — 캐시 + 경량 추출로 속도 개선"""
    data = request.get_json(silent=True) or {}
    url  = (data.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "URL을 입력해주세요."}), 400
    if not is_valid_youtube_url(url):
        return jsonify({"success": False, "error": "유효한 YouTube URL이 아닙니다."}), 400

    # 캐시 히트
    if url in info_cache:
        return jsonify({"success": True, **info_cache[url]})

    # ── 경량 옵션: 포맷 목록·자막 등 불필요한 항목 스킵 ──
    ydl_opts = {
        **BASE_OPTS,
        "skip_download": True,
        # 포맷 목록 전체 파싱 생략 → 가장 큰 속도 향상 포인트
        "extract_flat": False,   # False여야 title/thumb 등 메타만 빠르게 옴
        "youtube_include_dash_manifest": False,  # DASH manifest 다운 생략
        "writesubtitles": False,
        "writeautomaticsub": False,
        "format": "bestaudio",   # 단일 포맷만 resolve → 목록 파싱 최소화
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        duration = info.get("duration") or 0
        m, s = divmod(int(duration), 60)

        result = {
            "title":      info.get("title", "제목 없음"),
            "channel":    info.get("channel") or info.get("uploader", ""),
            "thumbnail":  info.get("thumbnail", ""),
            "duration":   f"{m}:{s:02d}",
            "view_count": f"{info.get('view_count', 0):,}",
        }
        info_cache[url] = result          # 캐시 저장
        return jsonify({"success": True, **result})

    except yt_dlp.utils.DownloadError as e:
        return jsonify({"success": False, "error": str(e)[:200]}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)[:200]}), 500


@app.route("/api/download", methods=["POST"])
def start_download():
    data    = request.get_json(silent=True) or {}
    url     = (data.get("url") or "").strip()
    fmt     = data.get("format", "mp4").lower()
    quality = data.get("quality", "best")

    if not url or not is_valid_youtube_url(url):
        return jsonify({"success": False, "error": "유효하지 않은 URL입니다."}), 400
    if fmt not in ("mp3", "mp4"):
        return jsonify({"success": False, "error": "지원하지 않는 포맷입니다."}), 400

    task_id = str(uuid.uuid4())
    threading.Thread(
        target=download_task, args=(task_id, url, fmt, quality), daemon=True
    ).start()

    return jsonify({"success": True, "task_id": task_id})


@app.route("/api/progress/<task_id>")
def get_progress(task_id: str):
    state = progress_store.get(task_id)
    if state is None:
        return jsonify({"status": "not_found"}), 404
    return jsonify(state)


@app.route("/api/download_file/<task_id>")
def download_file(task_id: str):
    state = progress_store.get(task_id)
    if not state or state.get("status") != "done":
        abort(404)
    fp = Path(state.get("filepath", ""))
    if not fp.exists():
        abort(404)
    return send_file(fp, as_attachment=True, download_name=fp.name)


@app.route("/api/cleanup", methods=["POST"])
def cleanup():
    data    = request.get_json(silent=True) or {}
    task_id = data.get("task_id", "")
    if task_id and task_id in progress_store:
        shutil.rmtree(DOWNLOAD_DIR / task_id, ignore_errors=True)
        del progress_store[task_id]
    return jsonify({"success": True})


if __name__ == "__main__":
    print("=" * 55)
    print("  🎬 YouTube Downloader — HD교육컨설팅")
    print("=" * 55)
    print("  http://localhost:5000 에서 접속하세요")
    print("=" * 55)
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)
