from flask import Flask, request, render_template
import os

app = Flask(__name__)

# 업로드된 이미지 저장 폴더 설정
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 기본 페이지: 이미지 업로드 폼
@app.route('/')
def index():
    return render_template('index.html')

# 추론 요청 처리
@app.route('/predict', methods=['POST'])
def predict():
    if 'image' not in request.files:
        return "No file part"

    file = request.files['image']
    if file.filename == '':
        return "No selected file"

    # 이미지 저장
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # YOLO 추론은 아직 연결 안 함. 더미 텍스트로 결과 반환
    result = "YOLO 모델 결과: (예시 라벨)"

    # 결과 페이지로 이미지와 텍스트 전달
    return render_template('result.html', result=result, image_url=filepath)

# Render 플랫폼 호환을 위해 host/port 지정
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
