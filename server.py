from flask import Flask, request, render_template
import os

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
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

    result = "YOLO 모델 결과: (예시 라벨)"
    return render_template('result.html', result=result, image_url=filepath)

if __name__ == '__main__':
    # 🔥 Render가 제공하는 포트를 사용!
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
