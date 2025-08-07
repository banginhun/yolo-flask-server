from flask import Flask, request, render_template
import os

# ✅ Flask 앱 생성
app = Flask(__name__)

# ✅ 이미지 저장 폴더 설정
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ✅ 최근 업로드 이미지 추적용 전역 변수
last_uploaded_filename = None

@app.route('/')
def index():
    return render_template('index.html', last_image=last_uploaded_filename)

@app.route('/predict', methods=['POST'])
def predict():
    global last_uploaded_filename

    if 'image' not in request.files:
        return "No file part"
    file = request.files['image']
    if file.filename == '':
        return "No selected file"

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # 최근 업로드 이미지 기억
    last_uploaded_filename = file.filename

    result = "YOLO 모델 결과: (예시 라벨)"
    return render_template('result.html', result=result, image_url=filepath)

# ✅ 로컬에서 테스트할 경우만 실행 (Render는 gunicorn 사용)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
