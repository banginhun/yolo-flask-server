import os, uuid, time
from datetime import datetime
from tempfile import NamedTemporaryFile
from flask import (
    Flask, request, abort, send_from_directory,
    render_template, jsonify, redirect, url_for
)
from werkzeug.utils import secure_filename

# 기본 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 설정
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "example-secret")   # 라파와 동일하게 맞추면 간단 인증
MAX_KEEP   = int(os.environ.get("MAX_KEEP", "2000"))          # 보관 최대 개수(오래된 것 자동 삭제)
app = Flask(__name__, static_folder="static", template_folder="templates")

# 업로드 제한 (과도한 큰 파일 방지)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB

# ---------- 유틸 ----------
def _safe_name(stem: str) -> str:
    stem = stem.replace(":", "_").replace("/", "_").replace("\\", "_")
    return secure_filename(stem) + ".jpg"

def _is_latest(fname: str) -> bool:
    return fname.startswith("latest_") and fname.lower().endswith(".jpg")

def _list_images_sorted():
    files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".jpg")]
    files = [f for f in files if not _is_latest(f)]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)), reverse=True)
    return files

def _atomic_write_bytes(dst_path: str, data: bytes):
    # 같은 디렉토리 임시파일 → 원자적 교체
    with NamedTemporaryFile(dir=os.path.dirname(dst_path), delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, dst_path)

def _prune_if_needed():
    files = _list_images_sorted()
    if len(files) <= MAX_KEEP:
        return
    for f in files[MAX_KEEP:]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, f))
        except Exception:
            pass

# ---------- 라우트 ----------
@app.route("/", methods=["GET"])
def index():
    # 최신(전체) + 장비별 최신 목록
    latest_all = "latest_all.jpg" if os.path.exists(os.path.join(UPLOAD_DIR, "latest_all.jpg")) else None
    device_latest = []
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith("latest_") and f != "latest_all.jpg" and f.lower().endswith(".jpg"):
            device_latest.append(f)
    device_latest.sort()
    return render_template("index.html", latest_all=latest_all, device_latest=device_latest)

@app.route("/gallery", methods=["GET"])
def gallery():
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        size = min(max(int(request.args.get("size", 50)), 1), 200)
    except ValueError:
        size = 50

    files = _list_images_sorted()
    total = len(files)
    start = (page - 1) * size
    end = start + size
    page_files = files[start:end]

    return render_template(
        "gallery.html",
        files=page_files,
        page=page,
        size=size,
        total=total,
        has_prev=page > 1,
        has_next=end < total
    )

@app.route("/api/recent", methods=["GET"])
def api_recent():
    limit = min(int(request.args.get("limit", 100)), 1000)
    files = _list_images_sorted()[:limit]
    items = []
    for f in files:
        p = os.path.join(UPLOAD_DIR, f)
        items.append({
            "file": f,
            "url": url_for("serve_upload", filename=f),
            "mtime": os.path.getmtime(p)
        })
    return jsonify(items)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/upload", methods=["POST"])
def upload():
    # 간단 인증(옵션)
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)

    if "image" not in request.files:
        abort(400, "no image")

    f = request.files["image"]
    raw = f.read()  # 메모리로 읽어서 1회 쓰기

    ts = request.form.get("ts") or datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    device = (request.headers.get("X-Device-Id") or "unknown").strip() or "unknown"

    # 고유 파일명(동시 업로드 충돌 방지: ts + uuid)
    fname = _safe_name(f"{device}_{ts}_{uuid.uuid4().hex[:8]}")
    save_path = os.path.join(UPLOAD_DIR, fname)
    _atomic_write_bytes(save_path, raw)

    # latest 갱신(전체/장비별) - 원자적 교체
    _atomic_write_bytes(os.path.join(UPLOAD_DIR, "latest_all.jpg"), raw)
    _atomic_write_bytes(os.path.join(UPLOAD_DIR, f"latest_{device}.jpg"), raw)

    _prune_if_needed()
    return ("", 204)

@app.route("/delete", methods=["POST"])
def delete_image():
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)
    name = request.form.get("file")
    if not name:
        abort(400, "no file")
    p = os.path.join(UPLOAD_DIR, os.path.basename(name))
    if os.path.isfile(p) and not _is_latest(os.path.basename(p)):
        os.remove(p)
    return redirect(url_for("gallery"))

if __name__ == "__main__":
    # 로컬 테스트용(운영은 gunicorn 권장)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))

def _list_images_sorted():
    files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".jpg")]
    files = [f for f in files if not _is_latest(f)]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)), reverse=True)
    return files

def _device_from_filename(fname: str) -> str:
    # 저장 규칙: {device}_{ts}_{uuid}.jpg
    try:
        return fname.split("_", 1)[0]
    except Exception:
        return "unknown"

def _device_list():
    devices = sorted({ _device_from_filename(f) for f in _list_images_sorted() })
    return devices

@app.route("/gallery", methods=["GET"])
def gallery():
    # 장비 필터
    device = request.args.get("device", "").strip()
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    try:
        size = min(max(int(request.args.get("size", 50)), 1), 200)
    except ValueError:
        size = 50

    files = _list_images_sorted()
    if device:
        files = [f for f in files if _device_from_filename(f) == device]

    total = len(files)
    start = (page - 1) * size
    end = start + size
    page_files = files[start:end]

    return render_template(
        "gallery.html",
        files=page_files,
        page=page,
        size=size,
        total=total,
        has_prev=page > 1,
        has_next=end < total,
        devices=_device_list(),
        current_device=device
    )

@app.route("/gallery/split", methods=["GET"])
def gallery_split():
    # 장비별로 최신 N장씩 나눠서 한 화면에
    try:
        n = min(max(int(request.args.get("n", 30)), 1), 200)
    except ValueError:
        n = 30

    files = _list_images_sorted()
    groups = {}
    for f in files:
        d = _device_from_filename(f)
        groups.setdefault(d, [])
        if len(groups[d]) < n:
            groups[d].append(f)
    # 정렬: 장비명 알파벳순
    ordered = [(d, groups[d]) for d in sorted(groups.keys())]

    return render_template("gallery_split.html", groups=ordered, n=n)
