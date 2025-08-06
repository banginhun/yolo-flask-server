from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def index():
    return "서버 연결 성공!"

@app.route('/upload', methods=['POST'])
def upload_image():
    image = request.files['image']
    print(f"[RECEIVED] {image.filename}")
    return "이미지 수신 완료!"
