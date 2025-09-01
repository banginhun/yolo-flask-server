# server.py
import os, uuid, time, csv
from datetime import datetime
from tempfile import NamedTemporaryFile
from collections import deque
from io import BytesIO
from pathlib import Path

from flask import (
    Flask, request, abort, send_from_directory,
    render_template, render_template_string, jsonify, redirect, url_for, Blueprint
)
from werkzeug.utils import secure_filename

# Pillow(이미지 오버레이용)
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

# ---------- 기본 설정 ----------
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")

# 환경 변수
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "example-secret")  # 라파/마스터와 동일하게
MAX_KEEP   = int(os.environ.get("MAX_KEEP", "2000"))         # 보관 최대 개수
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024          # 10MB 업로드 제한

# ---------- 제어 큐 ----------
cmd_q = deque()  # 서버 메모리 내 간단 큐

# ---------- 유틸 ----------
def _safe_name(stem: str) -> str:
    """파일명 안전화 + .jpg 부착"""
    stem = stem.replace(":", "_").replace("/", "_").replace("\\", "_")
    return secure_filename(stem) + ".jpg"

def _is_latest(fname: str) -> bool:
    return fname.startswith("latest_") and fname.lower().endswith(".jpg")

def _atomic_write_bytes(dst_path: str, data: bytes):
    """같은 디렉토리 임시파일에 쓰고 os.replace로 원자적 갱신"""
    with NamedTemporaryFile(dir=os.path.dirname(dst_path), delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_name = tmp.name
    os.replace(tmp_name, dst_path)

def _list_images_sorted():
    """latest_* 제외, 최신순 정렬"""
    files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".jpg")]
    files = [f for f in files if not _is_latest(f)]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)), reverse=True)
    return files

def _device_from_filename(fname: str) -> str:
    try:
        return fname.split("_", 1)[0]
    except Exception:
        return "unknown"

def _device_list():
    return sorted({_device_from_filename(f) for f in _list_images_sorted()})

def _prune_if_needed():
    files = _list_images_sorted()
    if len(files) <= MAX_KEEP:
        return
    for f in files[MAX_KEEP:]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, f))
        except Exception:
            pass

def _overlay_frame_idx(jpg_bytes: bytes, text: str) -> bytes:
    """프레임 번호 텍스트를 이미지에 오버레이"""
    if not PIL_AVAILABLE or not text:
        return jpg_bytes
    try:
        im = Image.open(BytesIO(jpg_bytes)).convert("RGB")
        W, H = im.size
        draw = ImageDraw.Draw(im)

        base = max(min(W, H), 1)
        font_size = max(int(base * 0.045), 16)
        pad = max(int(font_size * 0.4), 6)

        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        if font is not None:
            tw, th = draw.textbbox((0, 0), text, font=font)[2:]
        else:
            # fallback 추정
            tw, th = len(text) * font_size * 0.6, font_size

        x, y = pad, pad
        box = [x - pad, y - pad, x + int(tw) + pad, y + int(th) + pad]
        draw.rectangle(box, fill=(0, 0, 0, 180))
        draw.text((x, y), text, fill=(255, 255, 255), font=font)

        out = BytesIO()
        im.save(out, format="JPEG", quality=90)
        return out.getvalue()
    except Exception:
        return jpg_bytes

# ---------- 페이지 ----------
@app.route("/", methods=["GET"])
def index():
    latest_all = "latest_all.jpg" if os.path.exists(os.path.join(UPLOAD_DIR, "latest_all.jpg")) else None
    device_latest = []
    for f in os.listdir(UPLOAD_DIR):
        if f.startswith("latest_") and f != "latest_all.jpg" and f.lower().endswith(".jpg"):
            device_latest.append(f)
    device_latest.sort()
    return render_template("index.html", latest_all=latest_all, device_latest=device_latest)

@app.route("/gallery", methods=["GET"])
def gallery():
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
    ordered = [(d, groups[d]) for d in sorted(groups.keys())]
    return render_template("gallery_split.html", groups=ordered, n=n)

# ---------- 업로드(기존) ----------
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
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)
    if "image" not in request.files:
        abort(400, "no image")
    raw = request.files["image"].read()

    ts = request.form.get("ts") or datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    device = (request.headers.get("X-Device-Id") or request.headers.get("X-Cam-Id") or "unknown").strip() or "unknown"

    frame_idx = request.form.get("frame_idx") or request.headers.get("X-Frame-Idx")
    try:
        frame_idx = str(int(frame_idx))
    except Exception:
        frame_idx = None

    overlay_flag = (request.form.get("overlay_frame") or request.headers.get("X-Overlay-Frame") or "").strip().lower()
    overlay = overlay_flag in ("1", "true", "yes", "y")

    if frame_idx is not None:
        stem = f"{device}_{ts}_f{frame_idx}_{uuid.uuid4().hex[:8]}"
    else:
        stem = f"{device}_{ts}_{uuid.uuid4().hex[:8]}"
    fname = _safe_name(stem)
    save_path = os.path.join(UPLOAD_DIR, fname)

    to_write = raw
    if overlay and frame_idx is not None:
        to_write = _overlay_frame_idx(raw, f"f{frame_idx}")

    _atomic_write_bytes(save_path, to_write)

    _atomic_write_bytes(os.path.join(UPLOAD_DIR, "latest_all.jpg"), to_write)
    _atomic_write_bytes(os.path.join(UPLOAD_DIR, f"latest_{device}.jpg"), to_write)

    _prune_if_needed()
    return ("", 204)

# ---------- START/STOP 제어 ----------
@app.get("/control_panel")
def control_panel():
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)
    return render_template_string("""
<!doctype html><meta charset="utf-8">
<h3>라파 동기 캡처 컨트롤</h3>
<button onclick="send('START')">START</button>
<button onclick="send('STOP')">STOP</button>
<script>
async function send(cmd){
  const r = await fetch('/control', {
    method:'POST',
    headers:{'Content-Type':'application/json','X-Auth-Token':'{{token}}'},
    body: JSON.stringify({cmd})
  });
  alert(cmd + ' sent: ' + r.status);
}
</script>
""", token=AUTH_TOKEN)

@app.post("/control")
def control():
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)
    data = request.get_json(silent=True) or {}
    cmd = (data.get("cmd") or "").upper()
    if cmd not in ("START", "STOP"):
        abort(400, "bad cmd")
    cmd_q.append({"cmd": cmd, "ts": time.time()})
    return jsonify(ok=True)

@app.get("/pop_cmd")
def pop_cmd():
    if AUTH_TOKEN and request.headers.get("X-Auth-Token") != AUTH_TOKEN:
        abort(401)
    if cmd_q:
        return jsonify(cmd_q.popleft())
    return jsonify({"cmd": "NONE"})

# ---------- Dual-cam 확장: /upload2 + /recent + /latest-json ----------
recent_bp = Blueprint("recent_bp", __name__, template_folder="templates", static_folder="static")

BASE_PATH = Path(__file__).resolve().parent
D_UPLOAD_ROOT = BASE_PATH / "static" / "uploads"
D_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
LOG_CSV = D_UPLOAD_ROOT / "frames_log.csv"
if not LOG_CSV.exists():
    with LOG_CSV.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["recv_ts_ms","cam_id","cam_side","frame_idx","shot_ts_ns","sent_ts_ms","uuid","rel_path"])

def _safe_side(s: str) -> str:
    s = (s or "").lower().strip()
    return "left" if s == "left" else "right" if s == "right" else "unknown"

@recent_bp.route("/upload2", methods=["POST"])
def upload2():
    if "image" not in request.files:
        return jsonify({"ok": False, "error": "image required"}), 400
    image = request.files["image"]
    cam_id = request.form.get("cam_id", "RPI5")
    cam_side = _safe_side(request.form.get("cam_side"))
    frame_idx = int(request.form.get("frame_idx", -1))
    shot_ts_ns = int(request.form.get("shot_ts_ns", 0))
    sent_ts_ms = int(request.form.get("sent_ts_ms", 0))
    uuid_str = request.form.get("uuid") or str(uuid.uuid4())

    day = time.strftime("%Y%m%d")
    save_dir = D_UPLOAD_ROOT / cam_id / cam_side / day
    save_dir.mkdir(parents=True, exist_ok=True)
    recv_ts_ms = int(time.time() * 1000)
    base_name = f"{frame_idx if frame_idx>=0 else recv_ts_ms}_{uuid_str}.jpg"
    save_path = save_dir / base_name
    image.save(save_path)

    rel_path = str(save_path.relative_to(D_UPLOAD_ROOT).as_posix())
    with LOG_CSV.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([recv_ts_ms, cam_id, cam_side, frame_idx, shot_ts_ns, sent_ts_ms, uuid_str, rel_path])
    return jsonify({"ok": True, "saved": rel_path, "recv_ts_ms": recv_ts_ms}), 200

@recent_bp.route("/recent")
def recent_page():
    n = int(request.args.get("n", 30))
    rows = []
    if LOG_CSV.exists():
        with LOG_CSV.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: int(r["recv_ts_ms"]), reverse=True)
    left, right, unk = [], [], []
    for r in rows:
        item = {
            "recv_ts_ms": int(r["recv_ts_ms"]),
            "cam_id": r["cam_id"],
            "cam_side": r["cam_side"],
            "frame_idx": int(r["frame_idx"]),
            "shot_ts_ns": int(r["shot_ts_ns"]),
            "sent_ts_ms": int(r["sent_ts_ms"]),
            "uuid": r["uuid"],
            "rel_path": r["rel_path"],
            "url": "/static/uploads/" + r["rel_path"],
            "recv_hhmmss": time.strftime("%H:%M:%S", time.localtime(int(r["recv_ts_ms"])/1000.0)),
        }
        (left if r["cam_side"]=="left" else right if r["cam_side"]=="right" else unk).append(item)
    return render_template("recent.html", left_items=left[:n], right_items=right[:n], unknown_items=unk[:max(0, n//2)], total=len(rows))

@app.get("/latest-json")
def latest_json():
    latest = {"left": None, "right": None, "unknown": None}
    if LOG_CSV.exists():
        with LOG_CSV.open("r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows.sort(key=lambda r: int(r["recv_ts_ms"]), reverse=True)
        for r in rows:
            side = r["cam_side"]
            item = {
                "cam_id": r["cam_id"],
                "frame_idx": int(r["frame_idx"]),
                "recv_ts_ms": int(r["recv_ts_ms"]),
                "time": time.strftime("%H:%M:%S", time.localtime(int(r["recv_ts_ms"])/1000.0)),
                "url": "/static/uploads/" + r["rel_path"]
            }
            if side in ("left","right"):
                if latest[side] is None:
                    latest[side] = item
            else:
                if latest["unknown"] is None:
                    latest["unknown"] = item
            if latest["left"] and latest["right"]:
                break
    return jsonify({"ok": True, "latest": latest})

@recent_bp.route("/static/uploads/<path:filename>")
def serve_uploaded(filename):
    return send_from_directory(D_UPLOAD_ROOT, filename, as_attachment=False)

app.register_blueprint(recent_bp)

# ---------- 엔트리 ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
