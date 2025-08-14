import os
import time
from datetime import datetime
from flask import Flask, request, abort, send_from_directory, render_template, jsonify, redirect, url_for
from werkzeug.utils import secure_filename

# 기본 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "example-secret")  # 라파에서 X-Auth-Token 헤더로 전달
MAX_KEEP = int(os.environ.get("MAX_KEEP", "2000"))           # 저장 최대 개수 (넘치면 오래된 것부터 삭제)

app = Flask(__name__, static_folder="static", template_folder="templates")

def _safe_name(device: str, ts: str) -> str:
    # Render 환경에서 콜론(:) 등이 파일명에 있으면 문제될 수 있으니 치환
    base = f"{device}_{ts}".replace(":", "_").replace("/", "_").replace("\\", "_")
    return secure_filename(base) + ".jpg"

def _latest_path() -> str:
    return os.path.join(UPLOAD_DIR, "latest.jpg")

def _list_images_sorted():
    files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith(".jpg")]
    files = [f for f in files if f != "latest.jpg"]  # latest 링크/복사본 제외
    files.sort(key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)), reverse=True)
    return files

def _prune_if_needed():
    files = _list_images_sorted()
    if len(files) <= MAX_KEEP:
        return
    # 오래된 것부터 삭제
    for f in files[MAX_KEEP:]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, f))
        except Exception:
            pass

@app.route("/", methods=["GET"])
def index():
    # 최근 1장 표시
    latest_file = "latest.jpg" if os.path.exists(_latest_path()) else None
    return render_template("index.html", latest_file=latest_file)

@app.route("/gallery", methods=["GET"])
def gallery():
    # 간단한 페이지네이션 (?page=1&size=100)
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
    # mtime 같이 반환
    items = []
    for f in files:
        path = os.path.join(UPLOAD_DIR, f)
        items.append({
            "file": f,
            "url": url_for("serve_upload", filename=f),
            "mtime": os.path.getmtime(path)
        })
    return jsonify(items)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=False)

@app.route("/upload", methods=["POST"])
def upload():
    # 가벼운 인증
    token = request.headers.get("X-Auth-Token")
    if AUTH_TOKEN and token != AUTH_TOKEN:
        abort(401)

    if "image" not in request.files:
        abort(400, "no image")

    f = request.files["image"]
    ts = request.form.get("ts") or datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
    device = request.headers.get("X-Device-Id", "unknown")

    # 파일명 결정 및 저장
    fname = _safe_name(device, ts)
    save_path = os.path.join(UPLOAD_DIR, fname)
    f.save(save_path)

    # latest.jpg 업데이트(복사)
    try:
        # 가장 단순: 같은 디렉토리에 latest.jpg를 덮어쓰기
        with open(save_path, "rb") as src, open(_latest_path(), "wb") as dst:
            dst.write(src.read())
    except Exception:
        pass

    # 필요 시 여기서 바로 추론 파이프라인에 넘길 수 있음
    # run_inference(save_path)

    _prune_if_needed()

    # 라파는 응답 바디가 필요 없으므로 204
    return ("", 204)

@app.route("/delete", methods=["POST"])
def delete_image():
    # 웹에서 개별 삭제 버튼용(선택 사항)
    token = request.headers.get("X-Auth-Token")
    if AUTH_TOKEN and token != AUTH_TOKEN:
        abort(401)
    name = request.form.get("file")
    if not name:
        abort(400, "no file")
    p = os.path.join(UPLOAD_DIR, os.path.basename(name))
    if os.path.isfile(p) and os.path.basename(p) != "latest.jpg":
        os.remove(p)
    return redirect(url_for("gallery"))

if __name__ == "__main__":
    # Render는 gunicorn 사용 권장이지만, 로컬 테스트용
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
