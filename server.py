from flask import Flask, request, render_template, redirect, url_for
import os

app = Flask(__name__)
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    if 'image' not in request.files:
        return "No file part"

    file = request.files['image']
    if file.filename == '':
        return "No selected file"

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    # (임시) 추론 로직 대신 업로드된 이미지 경로만 넘김
    result = "YOLO 모델 결과: 라벨_테스트"

    return render_template('result.html', result=result, image_url=filepath)

if __name__ == '__main__':
    app.run()
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return '서버 잘 돌아감!'

